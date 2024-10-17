import requests


def getOrgs() -> str:
    url = sets.Get("orgsUrl", None)
    return url

def haveOrgs() -> bool:
    return getCon() is not None


class OrgS:
    def __init__(self):
        pass

    def post(self, body):
        url = getOrgs()
        if url is None:
            # TODO: Is this what we should return?
            return None
        data = json.dumps(body)
        response = requests.post(url, data=data)
        # TODO Handle creds
        # TODO Parse json response 

    def get(self, url, body):
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        base = getOrgs()
        if base is None:
            return None
        url = base + url
        response = requests.get(url, headers=headers)
        # TODO Handle creds
        # TODO Parse json response 

