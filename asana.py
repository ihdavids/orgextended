#!/usr/bin/env python
from __future__ import print_function
import base64
import requests
import six
import time


try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote

try:
    import simplejson as json
except ImportError:
    import json

from pprint import pprint


class AsanaException(Exception):
    """Wrap api specific errors"""
    pass

def get_class(str_or_class):
    """Accept a name or actual class object for a class in the current module.
    Return a class object."""
    if isinstance(str_or_class, str):
        return globals()[str_or_class]
    else:
        return str_or_class


class Closable(object):
    """
    Mixin for Trello objects for which you're allowed to PUT to <id>/closed.
    """
    def close(self):
        path = self._prefix + self._id + '/closed'
        params = {'value': 'true'}
        result = self._conn.put(path, params=params)


class Deletable(object):
    """
    Mixin for Asana objects which are allowed to be DELETEd.
    """
    def delete(self):
        path = self._prefix + self._id
        self._conn.delete(path)


class Field(object):
    """
    A simple field on a Trello object.  Maps the attribute to a key in the
    object's _data dict.
    """

    def __init__(self, key=None):
        self.key = key

    def __get__(self, instance, owner):
        # Accessing instance._data will trigger a fetch from Asana if the
        # _data attribute isn't already present.
        return instance._data[self.key]


class DateField(Field):

    def __get__(self, instance, owner):
        raw = super(DateField, self).__get__(instance, owner)
        return raw
        # return isodate.parse_datetime(raw)


class ObjectField(Field):
    """
    Maps an idSomething string attr on an object to another object type.
    """

    def __init__(self, key, cls):

        self.key = key
        self.cls = cls

    def __get__(self, instance, owner):
        return self.related_instance(instance._conn, instance._data[self.key])

    def related_instance(self, conn, obj_id):
        return get_class(self.cls)(conn, obj_id)


class ListField(ObjectField):
    """
    Like an ObjectField, but a list of them.  For fleshing out things like
    idMembers.
    """

    def __get__(self, instance, owner):
        ids = instance._data[self.key]
        if(ids != None):
            print(str(ids))
        conn = instance._conn
        return [self.related_instance(conn, id) for id in ids]


class SubList(object):
    """
    Kinda like a ListField, but for things listed under a URL subpath (like
    /boards/<id>/cards), as opposed to a list of ids in the document body
    itself.
    """

    def __init__(self, cls):
        # cls may be a name of a class, or the class itself
        self.cls = cls

        # A dict of sublists, by instance id
        self._lists = {}

    def __get__(self, instance, owner):
        if not instance._id in self._lists:
            cls = get_class(self.cls)
            path = instance._prefix + instance._id + cls._prefix
            data = json.loads(instance._conn.get(path))
            self._lists[instance._id] = [cls(instance._conn, d['id'], d) for d in data]
        return self._lists[instance._id]


class AsanaMeta(type):
    """
    Metaclass for LazyTrello objects, allowing documents to have Field
    attributes that know their names without them having to be explicitly
    passed to __init__.
    """
    def __new__(cls, name, bases, dct):
        for k, v in dct.items():
            # For every Field on the class that wasn't initted with an explicit
            # 'key', set the field name as the key.
            if isinstance(v, Field) and v.key is None:
                v.key = k
        return super(AsanaMeta, cls).__new__(cls, name, bases, dct)


class LazyAsana(object):
    """
    Parent class for Asana objects (cards, lists, boards, members, etc).  This
    should always be subclassed, never used directly.
    """

    __metaclass__ = AsanaMeta

    # The Asana API path where objects of this type may be found. eg '/projects/'
    @property
    def _prefix(self):
        raise NotImplementedError("LazyAsana subclasses MUST define a _prefix")

    def __init__(self, conn, obj_id, data=None):
        self._id = obj_id
        self._conn = conn
        self._path = self._prefix + obj_id

        # If we've been passed the data, then remember it and don't bother
        # fetching later.
        if data:
            self._data = data

    def __getattr__(self, attr):
        if attr == '_data':
            # Something is trying to access the _data attribute.  If we haven't
            # fetched data from Asana yet, do so now.  Cache the result on the
            # object.
            if not '_data' in self.__dict__:
                self._data = json.loads(self._conn._asana(self._path))

            return self._data
        else:
            raise AttributeError("%r object has no attribute %r" %
                                 (type(self).__name__, attr))

    def __unicode__(self):
        tmpl = u'<%(cls)s: %(name_or_id)s>'
        # If I have a name, use that
        if 'name' in self._data:
            return tmpl % {'cls': self.__class__.__name__,
                           'name_or_id': self._data['name']}

        return tmpl % {'cls': self.__class__.__name__,
                       'name_or_id': self._id}

    def __str__(self):
        return str(self.__unicode__())

    def __repr__(self):
        return str(self.__unicode__())

    def reload(self):
        self.__dict__.pop("_data", None)


class Project(LazyAsana, Closable):

    _prefix = 'projects/'

    url = Field('gid')
    name = Field('name')

    #actions = SubList('Action')
    #cards = SubList('Card')
    #checklists = SubList('Checklist')
    #lists = SubList('List')
    #members = SubList('Member')

    def goo(self):
        print(str(self._data))



class AsanaAPI(object):
    """Basic wrapper for the Asana api. For further information on the API
    itself see: http://developer.asana.com/documentation/
    """

    def __init__(self, apikey, debug=False):
        self.debug = debug
        self.asana_url = "https://app.asana.com/api"
        self.api_version = "1.0"
        self.aurl = "/".join([self.asana_url, self.api_version])
        self.apikey = apikey
        self.bauth = self.get_basic_auth()

    def get_basic_auth(self):
        """Get basic auth creds
        :returns: the basic auth string
        """
        s = six.b(self.apikey + ":")
        return base64.b64encode(s).rstrip()

    def handle_exception(self, r):
        """ Handle exceptions
        :param r: request object
        :param api_target: API URI path for requests
        :param data: payload
        :returns: 1 if exception was 429 (rate limit exceeded), otherwise, -1
        """
        if self.debug:
            print("-> Got: {0}".format(r.status_code))
            print("-> {0}".format(r.text))
        if (r.status_code == 429):
            self._handle_rate_limit(r)
            return 1
        else:
            raise AsanaException('Received non 2xx or 404 status code on call')

    def _handle_rate_limit(self, r):
        """ Sleep for length of retry time
        :param r: request object
        """
        retry_time = int(r.headers['Retry-After'])
        assert(retry_time > 0)
        if self.debug:
            print("-> Sleeping for {0} seconds".format(retry_time))
        time.sleep(retry_time)

    def _asana(self, api_target):
        """Peform a GET request
        :param api_target: API URI path for request
        """
        # TODO: Refactor to use requests.get params
        target = "/".join([self.aurl, quote(api_target, safe="/&=?")])
        if self.debug:
            print("-> Calling: {0}".format(target))
        r = requests.get(target, auth=(self.apikey, ""))
        if self._ok_status(r.status_code) and r.status_code is not 404:
            if r.headers['content-type'].split(';')[0] == 'application/json':
                if hasattr(r, 'text'):
                    return json.loads(r.text)['data']
                elif hasattr(r, 'content'):
                    return json.loads(r.content)['data']
                else:
                    raise AsanaException('Unknown format in response from api')
            else:
                raise AsanaException(
                    'Did not receive json from api: %s' % str(r))
        else:
            if (self.handle_exception(r) > 0):
                return self._asana(api_target)

    def _asana_delete(self, api_target):
        """Peform a DELETE request
        :param api_target: API URI path for request
        """
        target = "/".join([self.aurl, quote(api_target, safe="/&=?")])
        if self.debug:
            print("-> Calling: {0}".format(target))
        r = requests.delete(target, auth=(self.apikey, ""))
        if self._ok_status(r.status_code) and r.status_code is not 404:
            if r.headers['content-type'].split(';')[0] == 'application/json':
                if hasattr(r, 'text'):
                    return json.loads(r.text)['data']
                elif hasattr(r, 'content'):
                    return json.loads(r.content)['data']
                else:
                    raise AsanaException('Unknown format in response from api')
            else:
                raise AsanaException(
                    'Did not receive json from api: %s' % str(r))
        else:
            if (self.handle_exception(r) > 0):
                return self._asana_delete(api_target)

    def _asana_post(self, api_target, data=None, files=None):
        """Peform a POST request
        :param api_target: API URI path for request
        :param data: POST payload
        :param files: Optional file to upload
        """
        target = "/".join([self.aurl, api_target])
        if self.debug:
            print("-> Posting to: {0}".format(target))
            if data:
                print("-> Post payload:")
                pprint(data)
            if files:
                print("-> Posting file:")
                pprint(files)
        r = requests.post(
            target, auth=(self.apikey, ""), data=data, files=files)
        if self._ok_status(r.status_code) and r.status_code is not 404:
            if r.headers['content-type'].split(';')[0] == 'application/json':
                if hasattr(r, 'text'):
                    return json.loads(r.text)['data']
                elif hasattr(r, 'content'):
                    return json.loads(r.content)['data']
                else:
                    raise AsanaException('Unknown format in response from api')
            else:
                raise AsanaException(
                    'Did not receive json from api: %s' % str(r))
        else:
            if (self.handle_exception(r) > 0):
                return self._asana_post(api_target, data)

    def _asana_put(self, api_target, data):
        """Peform a PUT request
        :param api_target: API URI path for request
        :param data: PUT payload
        """
        target = "/".join([self.aurl, api_target])
        if self.debug:
            print("-> PUTting to: {0}".format(target))
            print("-> PUT payload:")
            pprint(data)
        r = requests.put(target, auth=(self.apikey, ""), data=data)
        if self._ok_status(r.status_code) and r.status_code is not 404:
            if r.headers['content-type'].split(';')[0] == 'application/json':
                if hasattr(r, 'text'):
                    return json.loads(r.text)['data']
                elif hasattr(r, 'content'):
                    return json.loads(r.content)['data']
                else:
                    raise AsanaException('Unknown format in response from api')
            else:
                raise AsanaException(
                    'Did not receive json from api: %s' % str(r))
        else:
            if (self.handle_exception(r) > 0):
                return self._asana_put(api_target, data)

    @classmethod
    def _ok_status(cls, status_code):
        """Check whether status_code is a ok status i.e. 2xx or 404"""
        status_code = int(status_code)
        if status_code / 200 == 1:
            return True
        elif status_code / 400 == 1:
            if status_code is 404:
                return True
            else:
                return False
        elif status_code is 500:
            return False

    def user_info(self, user_id="me"):
        """Obtain user info on yourself or other users.
        :param user_id: target user or self (default)
        """
        return self._asana('users/%s' % user_id)

    def list_users(self, workspace=None, filters=None):
        """List users
        :param workspace: list users in given workspace
        :param filters: Optional [] of filters you want to apply to listing
        """
        if workspace:
            return self._asana('workspaces/%s/users' % workspace)
        else:
            if filters:
                fkeys = [x.strip().lower() for x in filters]
                fields = ",".join(fkeys)
                return self._asana('users?opt_fields=%s' % fields)
            else:
                return self._asana('users')

    def list_tasks(self, workspace, assignee, include_archived=False,
                   completed_since=None, modified_since=None):
        """List tasks
        :param workspace: workspace id
        :param assignee: assignee
        :param include_archived: true to include archived tasks
        """
        # Sanitise our include_archived variable
        if include_archived:
            include_archived = "true"
        else:
            include_archived = "false"
        target = "tasks?workspace=%d&assignee=%s&include_archived=%s" % (
            workspace, assignee, include_archived)

        if completed_since:
            target += '&completed_since=%s' % completed_since
        if modified_since:
            target += '&modified_since=%s' % modified_since

        return self._asana(target)

    def get_task(self, task_id):
        """Get a task
        :param task_id: id# of task"""
        return self._asana("tasks/%d" % task_id)

    def get_subtasks(self, task_id):
        """Get subtasks associated with a given task
        :param task_id: id# of task"""
        return self._asana("tasks/%d/subtasks" % task_id)

    def list_projects(self, workspace=None, archived=None):
        """"List all projects in a workspace
        :param workspace: workspace whos projects you want to list
        :param archived: default None, filter by archived status
        """
        target = "projects"

        if archived is not None:
            target += "?archived=%d" % (archived)

        if workspace:
            target = "workspaces/%d/" % (workspace) + target

        return self._asana(target)

    def get_project(self, project_id):
        """Get project
        :param project_id: id# of project
        """
        return self._asana('projects/%d' % project_id)

    def get_project_tasks(self, project_id, include_archived=False):
        """Get project tasks
        :param project_id: id# of project
        :param include_archived: true to include archived tasks
        """
        # Sanitise our include_archived variable
        if include_archived:
            include_archived = "true"
        else:
            include_archived = "false"
        return self._asana('projects/%d/tasks?include_archived=%s' % (
            project_id, include_archived))

    def list_stories(self, task_id):
        """List stories for task
        :param task_id: id# of task
        """
        return self._asana('tasks/%d/stories' % task_id)

    def get_story(self, story_id):
        """Get story
        :param story_id: id# of story
        """
        return self._asana('stories/%d' % story_id)

    def list_workspaces(self):
        """List workspaces"""
        return self._asana('workspaces')

    def organization_teams(self, org_id):
        """Show all `teams <http://developer.asana.com/documentation/#teams>`
        you're member of in an
        `organization <https://asana.com/guide/workspaces/organizations>`.
        :param org_id organization id#
        """
        return self._asana('organizations/%d/teams' % org_id)

    def create_task(self, name, workspace, assignee=None, assignee_status=None,
                    completed=None, due_on=None, followers=None, notes=None,
                    projects=None):
        """Create a new task
        :param name: Name of task
        :param workspace: Workspace for task
        :param assignee: Optional assignee for task
        :param assignee_status: status
        :param completed: Whether this task is completed (defaults to False)
        :param due_on: Optional due date for task
        :param followers: Optional followers for task
        :param notes: Optional notes to add to task
        :param projects: Array of projects this task is associated with.
        """
        payload = {'name': name, 'workspace': workspace}
        if assignee:
            payload['assignee'] = assignee
        if assignee_status in ['inbox', 'later', 'today', 'upcoming']:
            payload['assignee_status'] = assignee_status
        if completed is not None:
            payload['completed'] = int(completed)
        if due_on:
            try:
                time.strptime(due_on, '%Y-%m-%d')
                payload['due_on'] = due_on
            except ValueError:
                raise AsanaException('Bad task due date: %s' % due_on)
        if followers:
            for pos, person in enumerate(followers):
                payload['followers[%d]' % pos] = person
        if projects:
            for pos, project in enumerate(projects):
                payload['projects[%d]' % pos] = project
        if notes:
            payload['notes'] = notes

        return self._asana_post('tasks', payload)

    def update_task(self, task, name=None, assignee=None, assignee_status=None,
                    completed=None, due_on=None, notes=None):
        """Update an existing task
        :param task: task to update
        :param name: Update task name
        :param assignee: Update assignee
        :param assignee_status: Update status
        :param completed: Update whether the task is completed
        :param due_on: Update due date
        :param notes: Update notes
        """
        payload = {}
        if name:
            payload['name'] = name
        if assignee:
            payload['assignee'] = assignee
        if assignee_status:
            payload['assignee_status'] = assignee_status
        if completed is not None:
            payload['completed'] = int(completed)
        if due_on:
            try:
                time.strptime(due_on, '%Y-%m-%d')
                payload['due_on'] = due_on
            except ValueError:
                raise AsanaException('Bad task due date: %s' % due_on)
        if notes:
            payload['notes'] = notes

        return self._asana_put('tasks/%s' % task, payload)

    def task_attachments(self, task_id):
        """Showing all attachments on a task.
        :param task_id: id# of a task
        """
        return self._asana('tasks/%d/attachments' % task_id)

    def get_attachment(self, attachment_id):
        """This method returns the full record for a single attachment.
        :param attachment_id: id# of an attachment
        """
        return self._asana('attachments/%d' % attachment_id)

    def upload_attachment(self, task_id, file_name, stream):
        """This method uploads an attachment to a task.
        :param task_id: id# of an a task
        :param file_name: attachment's file name
        :param stream: open file handle
        """
        return self._asana_post(
            'tasks/%d/attachments' % task_id,
            files={'file': (file_name, stream)}
        )

    def add_parent(self, task_id, parent_id):
        """Set the parent for an existing task.
        :param task_id: id# of a task
        :param parent_id: id# of a parent task
        """
        return self._asana_post('tasks/%s/setParent' % task_id,
                                {'parent': parent_id})

    def create_subtask(self, parent_id, name, completed=None, assignee=None,
                       notes=None, followers=None, assignee_status=None,
                       due_on=None):
        """Creates a task and sets it's parent.
        There is one noticeable distinction between
        creating task and assigning it a parent and
        creating a subtask. Latter doesn't get reflected
        in the project task list. Only in the parent task description.
        So using this method you can avoid polluting task list with subtasks.
        :param parent_id: id# of a task that subtask will be assigned to
        :param name: subtask name
        :param assignee: Optional user id# of subtask assignee
        :param notes: Optional subtask description
        :param followers: Optional followers for subtask
        :param assignee_status: Optional status for assignee
        :param due_on: Due date in format YYYY-MM-DD"""
        payload = {'name': name}
        if assignee:
            payload['assignee'] = assignee
        if followers:
            for pos, person in enumerate(followers):
                payload['followers[%d]' % pos] = person
        if notes:
            payload['notes'] = notes
        if completed is not None:
            payload['completed'] = int(completed)
        if assignee_status in ['inbox', 'later', 'today', 'upcoming']:
            payload['assignee_status'] = assignee_status
        if due_on:
            try:
                time.strptime(due_on, '%Y-%m-%d')
                payload['due_on'] = due_on
            except ValueError:
                raise AsanaException('Bad task due date: %s' % due_on)
        return self._asana_post('tasks/%s/subtasks' % parent_id, payload)

    def create_project(self, name, workspace, team=None,
                       notes=None, archived=None):
        """Create a new project
        :param name: Name of project
        :param workspace: Workspace for task
        :param team: Optional id/name of the team this project is shared with
        :param notes: Optional notes to add
        :param archived: Whether or not project is archived (defaults to False)
        """
        payload = {'name': name, 'workspace': workspace, 'team': team}
        if notes:
            payload['notes'] = notes
        if archived is not None:
            payload['archived'] = int(archived)
        return self._asana_post('projects', payload)

    def update_project(self, project_id, name=None, notes=None,
                       archived=None):
        """Update project
        :param project_id: id# of project
        :param name: Update name
        :param notes: Update notes
        :param archived: Update archive status
        """
        payload = {}
        if name:
            payload['name'] = name
        if notes:
            payload['notes'] = notes
        if archived is not None:
            payload['archived'] = int(archived)
        return self._asana_put('projects/%s' % project_id, payload)

    def delete_project(self, project_id):
        """Delete project
        :param project_id: id# of project
        """
        return self._asana_delete('projects/%s' % project_id)

    def update_workspace(self, workspace_id, name):
        """Update workspace
        :param workspace_id: id# of workspace
        :param name: Update name
        """
        payload = {'name': name}
        return self._asana_put('workspaces/%s' % workspace_id, payload)

    def add_project_task(self, task_id, project_id):
        """Add project task
        :param task_id: id# of task
        :param project_id: id# of project
        """
        return self._asana_post('tasks/%d/addProject' % task_id,
                                {'project': project_id})

    def rm_project_task(self, task_id, project_id):
        """Remove a project from task
        :param task_id: id# of task
        :param project_id: id# of project
        """
        return self._asana_post('tasks/%d/removeProject' % task_id,
                                {'project': project_id})

    def add_story(self, task_id, text):
        """Add a story to task
        :param task_id: id# of task
        :param text: story contents
        """
        return self._asana_post('tasks/%d/stories' % task_id, {'text': text})

    def add_tag_task(self, task_id, tag_id):
        """Tag a task
        :param task_id: id# of task
        :param tag_id: id# of tag to add
        """
        return self._asana_post('tasks/%d/addTag' % task_id, {'tag': tag_id})

    def rm_tag_task(self, task_id, tag_id):
        """Remove a tag from a task.
        :param task_id: id# of task
        :param tag_id: id# of tag to remove
        """
        return self._asana_post('tasks/%d/removeTag' %
                                task_id, {'tag': tag_id})

    def get_task_tags(self, task_id):
        """List tags that are associated with a task.
        :param task_id: id# of task
        """
        return self._asana('tasks/%d/tags' % task_id)

    def get_tags(self, workspace):
        """Get available tags for workspace
        :param workspace: id# of workspace
        """
        return self._asana('workspaces/%d/tags' % workspace)

    def get_tag_tasks(self, tag_id):
        """Get tasks for a tag
        :param tag_id: id# of task
        """
        return self._asana('tags/%d/tasks' % tag_id)

    def create_tag(self, tag, workspace):
        """Create tag
        :param tag_name: name of the tag to be created
        :param workspace: id# of workspace in which tag is to be created
        """
        payload = {'name': tag, 'workspace': workspace}

        return self._asana_post('tags', payload)


