# *python-dateutil* module for Package Control

This is a mirror of the [python-dateutil](https://github.com/dateutil/dateutil) module, created for using it as *dependency* in [Package Control](http://packagecontrol.io) for [Sublime Text](http://sublimetext.com/).


this repo | pypi
---- | ----
![latest tag](https://img.shields.io/github/tag/vovkkk/sublime-dateutil.svg) | [![pypi](https://img.shields.io/pypi/v/python-dateutil.svg)](https://pypi.python.org/pypi/python-dateutil)


## How to use

1. Create a `dependencies.json` file in your package root with the following contents:

    ```js
    {
       "*": {
          "*": [
             "dateutil"
          ]
       }
    }
    ```

2. Run the **Package Control: Satisfy Dependencies** command via command palette

3. Import as you [usually do](https://dateutil.readthedocs.io/en/stable/#quick-example) in stand-alone Python, e.g.

    ```python
    from dateutil import parser
    ```

See also:
[Documentation on Dependencies ](https://packagecontrol.io/docs/dependencies)

## License

[Simplified BSD](all/LICENSE)
