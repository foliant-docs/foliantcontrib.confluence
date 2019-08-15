# confluence_upload backend for Foliant

confluence_upload backend generates a confluence article and uploads it into your confluence server. With it you can create and edit pages in Confluence based on your Foliant project.

It also has a feature of restoring the user inline comments, added for the article, even after the commented fragment was changed.

This backend adds the `confluence` target for your Foliant `make` command.

## Installation

```bash
$ pip install foliantcontrib.confluence_upload
```

> confluence_upload backend requires [Pandoc](https://pandoc.org/) to be installed in your system.

## Usage

To upload a Foliant project to Confluence server use this command:

```bash
$ foliant make confluence
Parsing config... Done
Making confluence... Done
────────────────────
Result: https://my_confluence_server.org/pages/viewpage.action?pageId=123
```

## Config

You have to set up a config for this backend to work properly.

Specify all options in `backend_config.confluence_upload` section:

```yaml
backend_config:
  confluence_upload:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    id: 124443
    title: Title of the page
    space_key: "~user"
    parent_id: 124442
```

`host`
:   **Required** Host of your confluence server.

`login`
:   **Required** Login of the user who has the rights to create and update pages.

`password`
:   **Required** Password of the user.

`id`
:   ID of the page into which the content will be uploaded. *Only for already existing pages*

`title`
:   Title of the page to be created or updated.

> Remember that titles of the pages in one space are unique in Confluence.

`space_key`
:   The key of the space where the page will be created/edited.

`parent_id`
:   ID of the parent page under which the new one should be created. *Only for not yet existing pages*.

## Creating pages with confluence_upload

If you want a new page to be created for content in your Foliant project, just supply the title and the space key in the config. Remember that in Confluence page titles are unique inside one space. If you use a title of already existing page, confluence_upload will attempt to edit it and replace its content with your project.

Example config for this situation is:

```yaml
backend_config:
  confluence_upload:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    title: My unique title
    space_key: "~user"
```

Now if you change the title in your config, confluence_upload will *create a new page with the new title*, the old one remaining intact.

If you want to change the title of your page, the answer is in the following section.

## Updating pages with confluence_upload

Generally to update the page contents you may use the same config you used to create it (see previous section).

Also, you can just specify the id of your page, this way after build its contents will be updated.

```yaml
backend_config:
  confluence_upload:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    id: 124443
```

This is also *the only* way to edit a page title. If `title` param is specified, confluence_upload will attempt to change the page's title to the new one:

```yaml
backend_config:
  confluence_upload:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    id: 124443
    title: New unique title
```
