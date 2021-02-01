# Org Extended

  ![Org](https://orgmode.org/resources/img/org-mode-unicorn.svg)

  OrgMode is a lifestyle. While I like sublime, living without Org Mode has been something 
  that has driven me back to Emacs over and over again. I finally decided that I might take a stab
  at building a usable orgmode plugin for sublime.

  ![Start](./images/orgstart.gif)

  NOTE: To get setup, please jump down the Setup link below.
  
  When people show off org, they often just show off some folding
  and the ability to tab cycle a headings tree. This often leads people
  to compare org with Markdown. Org IS a markup and document interchange
  format like markdown, but it is also much more.

  ![Folding](./images/orgstartfolding.gif)

  Fundamentally org mode is *2* very /different/ things and fairly hard to describe:

  1. Org Files - A text based document markup language similar to markdown.
  2. Org Mode  - A wide variety of tools for operating on and working with collections of these files.
  3. Org Extensions - I know I said 2 but Org Mode has a wide variety of tools built around the mode and api's extending it in many creative ways. Although not org mode itself most people refer to these tools when they think of org mode.

  Org Mode can and has been used for a large variety of things:

  + A Personal Wiki
  + Professional Notes
  + Time Tracking and Billing
  + Documentation
  + Research Papers - Dynamic Documents
  + Literate Programming
  + Personal Agenda
  + Project Planning
  + As a blogging tool
  + Website content management 
  + A means of planning and managing a budget with ledger mode
  + As a process and memory aid for IT professionals
  + As a self documenting configuration file for emacs itself (and other things).
  + Many many more things


  What makes Org Mode so versatile is the deceptive simplicity of the format
  the flexibility of the simple markup and the the depth of the tools and API's provided around that format.

  At times I have wondered why I shouldn't just use markdown? It is a much more widely popular markup system.
  There is no reason markdown could not be extended to become exactly what Org Mode
  has become, but markdown is not quite as flexible with its meta data and has not had the same degree of *cult*
  following so has yet to evolve into something like Org.

  I hope to go beyond simply the file format and bring some of the actual Mode to Sublime.
  I simply cannot build the entire thing, but I hope we can build something unique and amazing
  in sublime, in its own right.

# This Plugin

  - [Basic Structure](https://github.com/ihdavids/orgextended_docs/blob/master/orgextended.org) - Basic file structure
  - [Setup](https://github.com/ihdavids/orgextended_docs/blob/master/setup.org) - Sublime Setup
  - [Editing](https://github.com/ihdavids/orgextended_docs/blob/master/editing.org) - Editing your org file
  - [Lists](https://github.com/ihdavids/orgextended_docs/blob/master/lists.org) - Supported lists in an org file
  - [Folding](https://github.com/ihdavids/orgextended_docs/blob/master/folding.org) - Jumping from the full view to a folded representation.
  - [Links](https://github.com/ihdavids/orgextended_docs/blob/master/links.org) - Jumping within and without.
  - [Navigation](https://github.com/ihdavids/orgextended_docs/blob/master/navigation.org) - Powerful ways of navigating your org files.
  - [Capture, Refile, Archive](https://github.com/ihdavids/orgextended_docs/blob/master/capture.org) - Save ideas fast.
  - [Exporting](https://github.com/ihdavids/orgextended_docs/blob/master/exporting.org) - Converting from org to other things.
  - [Properties and Drawers](https://github.com/ihdavids/orgextended_docs/blob/master/properties.org) - Metadata within a heading
  - [Scheduling](https://github.com/ihdavids/orgextended_docs/blob/master/dates.org) - Dates and times
  - [Time Tracking](https://github.com/ihdavids/orgextended_docs/blob/master/clocking.org) - Clocking and clock reports
  - [Dynamic Blocks](https://github.com/ihdavids/orgextended_docs/blob/master/dynamicblocks.org) - Run arbitrary code
  - [Agenda](https://github.com/ihdavids/orgextended_docs/blob/master/agenda.org) - Keeping track of your day.

  The full documentation for this plugin can be found at: [Docs](https://github.com/ihdavids/orgextended_docs)

# Thank You
  I have shamelessly built this plugin on the backs of some excellent plugins and libraries.

  - The original orgmode plugin - This work was exceptional, OrgExtended is a tribute to that work and consumes some of it.
  - sublime_ZK - The inline image preview is entirely due to the Markdown ZK plugin. 
    [ZK](https://github.com/renerocksai/sublime_zk) Thank you renerocksai for pointing out that phantoms can be used for image preview.
  - Table Edit - For now this excellent plugin is a dependency and the basis by which we offer Org style table editing.
  	In a fiture version we may look to consume the package and own table editing to facilitate expressions and some of the more
  	advanced org table tools, but for now, thank you for making this excellent plugin!
  - pymitter - a great little event library for python.
  - highlightjs - a wonderful highlighting library for html.
  - pandoc - a great command line tool for converting formats.


# References
  To help get you started on your Org journey
  Here are some useful external links:

- [The Org Manual](https://orgmode.org/manual/) - The official source of truth for all things orgmode
- [Org Mode 4 Beginners](https://orgmode.org/worg/org-tutorials/org4beginners.html) - An introduction
- [David O'Tools Introduction](https://orgmode.org/worg/org-tutorials/orgtutorial_dto.html) - Yet another intro
- [The Many Uses of Org Mode](https://thoughtbot.com/blog/the-many-uses-of-org-mode)
- [More Uses](https://kitchingroup.cheme.cmu.edu/blog/2014/08/08/What-we-are-using-org-mode-for/)
- [Your Life In Plain Text](http://doc.norang.ca/org-mode.html) - A wonderful reference on one mans journey to use orgmode to improve his life
