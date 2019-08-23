![](https://img.shields.io/pypi/v/foliantcontrib.confluence.svg)

# Confluence backend for Foliant

Confluence backend generates a confluence article and uploads it into your confluence server. With it you can create and edit pages in Confluence based on your Foliant project.

It also has a feature of restoring the user inline comments, added for the article, even after the commented fragment was changed.

This backend adds the `confluence` target for your Foliant `make` command.

## Installation

```bash
$ pip install foliantcontrib.confluence
```

> The backend requires [Pandoc](https://pandoc.org/) to be installed in your system. Pandoc is needed to convert Markdown into HTML.

## Usage

To upload a Foliant project to Confluence server use `make confluence` command:

```bash
$ foliant make confluence
Parsing config... Done
Making confluence... Done
────────────────────
Result: https://my_confluence_server.org/pages/viewpage.action?pageId=123
```

## Config

You have to set up a config for this backend to work properly.

Specify all options in `backend_config.confluence` section:

```yaml
backend_config:
  confluence:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    mode: single
    toc: false
    id: 124443
    title: Title of the page
    space_key: "~user"
    parent_id: 124442
    pandoc_path: pandoc
```

`host`
:   **Required** Host of your confluence server.

`login`
:   Login of the user who has the rights to create and update pages. If login is not supplied, it will be prompted during build

`password`
:   Password of the user. If password is not supplied, it will be prompted during build

`mode`
:   One of: `single`, `multiple`. In single mode backend uploads the whole Foliant project into specified Confluence page. In multiple mode backend uploads several chapters into separate Confluecnce pages defined with metadata. More info in the **Modes** section. Default: `single`.

`toc`
:   Set to `true` to add table of contents into the beginning of the document. Default: `false`

`id`
:   ID of the page into which the content will be uploaded (use only with `single` mode). *Only for already existing pages*

`title`
:   Title of the page to be created or updated (use only with `single` mode).

> Remember that titles of the pages in one space are unique in Confluence.

`space_key`
:   The key of the space where the page(s) will be created/edited.

`parent_id`
:   ID of the parent page under which the new one(s) should be created. *Only for not yet existing pages*.

`pandoc_path`
:   Path to Pandoc executable (Pandoc is used to convert Markdown into HTML).

## Modes

Backend confluence can work in two modes:

`single` — the whole project is flattened and uploaded into a single Confluence page;
`multiple` — you may upload several chapters of your project into separate Confluence pages.

### single mode

To use single mode first supply an option `mode: single` in foliant.yml, and then specify all the page properties (id or title & space) in the same foliant.yml config file. The project will be built, flattened into a single page and uploaded under the defined properties.

### multiple mode

With the power of multiple mode you may create or update several Confluence pages with just one `make` command.

To switch on multiple mode, add an option `mode: multiple` to your foliant.yml file. Next, add properties defining the confluence page (like id or title & space) to the meta section of each chapter that you want to upload.

Meta section is a YAML field-value section in the beginning of the document, which is defined like this:

```yaml
---
field: value
field2: value
---

Your chapter md-content
```

So if you want to upload a chapter into confluence, add something like this into the beginning of it:

```yaml
---
title: My confluence page
space_key: "~user"
confluence: true  # this is required
---

You chapter md-content
```

> Notice that we've also added a `confluence: true` key, which is required for chapter to be uploaded. If the key is `false` or is not defined, the backend will ignore this chapter.

After you've added properties to every page you want to be uploaded, run the same `make confluence` command:

```
$ foliant make confluence
Parsing config... Done
Making confluence... Done
────────────────────
Result:
https://my_confluence_server.org/pages/viewpage.action?pageId=1231
https://my_confluence_server.org/pages/viewpage.action?pageId=1232
https://my_confluence_server.org/pages/viewpage.action?pageId=1233
```

## Creating pages with confluence backend

If you want a new page to be created for content in your Foliant project, just supply the title and the space key in the config. Remember that in Confluence page titles are unique inside one space. If you use a title of already existing page, the backend will attempt to edit it and replace its content with your project.

Example config for this situation is:

```yaml
backend_config:
  confluence:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    title: My unique title
    space_key: "~user"
```

Now if you change the title in your config, confluence will *create a new page with the new title*, the old one remaining intact.

If you want to change the title of your page, the answer is in the following section.

## Updating pages with confluence backend

Generally to update the page contents you may use the same config you used to create it (see previous section).

Also, you can just specify the id of your page, this way after build its contents will be updated.

```yaml
backend_config:
  confluence:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    id: 124443
```

This is also *the only* way to edit a page title. If `title` param is specified, the backend will attempt to change the page's title to the new one:

```yaml
backend_config:
  confluence:
    host: 'https://my_confluence_server.org'
    login: user
    password: pass
    id: 124443
    title: New unique title
```
