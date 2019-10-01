![](https://img.shields.io/pypi/v/foliantcontrib.confluence.svg)

# Confluence backend for Foliant

Confluence backend generates confluence articles and uploads them on your confluence server. It can create and edit pages in Confluence with content based on your Foliant project.

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
Result:
https://my_confluence_server.org/pages/viewpage.action?pageId=123 (Page Title)
```

## Config

You have to set up correct config for this backend to work properly.

Specify all options in `backend_config.confluence` section:

```yaml
backend_config:
  confluence:
    host: 'https://my_confluence_server.org'
    login: user
    password: user_password
    id: 124443
    title: Title of the page
    space_key: "~user"
    parent_id: 124442
    parent_title: Parent
    notify_watchers: false
    toc: false
    restore_comments: true
    resolve_if_changed: false
    pandoc_path: pandoc
```

`host`
:   **Required** Host of your confluence server.

`login`
:   Login of the user who has permissions to create and update pages. If login is not supplied, it will be prompted during build.

`password`
:   Password of the user. If password is not supplied, it will be prompted during build.

`id`
:   ID of the page where the content will be uploaded. *Only for already existing pages*

`title`
:   Title of the page to be created or updated.

> Remember that page titles in the space have to be unique.

`space_key`
:   The space key where the page(s) will be created/edited. *Only for not yet existing pages*.

`parent_id`
:   ID of the parent page under which the new one(s) should be created. *Only for not yet existing pages*.

`parent_title`
:   Another way to define parent of the page. Lower priority than `paren_di`. Title of the parent page under which the new one(s) should be created. Parent should exist under the space_key specified. *Only for not yet existing pages*.

`notify_watchers`
:   If `true` — watchers will be notified that the page has changed. Default: `false`

`toc`
:   Set to `true` to add table of contents to the beginning of the document. Default: `false`

`restore_comments`
:   Attempt to restore inline comments near the same places after updating the page. Default: `true`

`resolve_if_changed`
:   Delete inline comment from the source if the commented text was changed. This will automatically mark comment as resolved. Default: `false`

`pandoc_path`
:   Path to Pandoc executable (Pandoc is used to convert Markdown into HTML).

# User's guide

## Uploading articles

By default if you specify `id` or `space_key` and `title` in foliant.yml, the whole project will be built and uploaded to this page.

If you wish to upload separate chapters into separate articles, you need to specify the respective `id` or `space_key` and `title` in *meta section* of the chapter.

Meta section is a YAML-formatted field-value section in the beginning of the document, which is defined like this:

```yaml
---
field: value
field2: value
---

Your chapter md-content
```

If you want to upload a chapter into confluence, add its properties under the `confluence` key like this:

```yaml
---
confluence:
    title: My confluence page
    space_key: "~user"
---

You chapter md-content
```

> **Important notice!**
> Both modes work together. If you specify the `id1` in foliant.yml and `id2` in chapter's meta — the whole project will be uploaded to the page with `id1`, and the specific chapter will also be uploaded to page with `id2`.

## Creating pages

If you want a new page to be created for content in your Foliant project, just supply in foliant.yml the space key and a title which does not yet exist in this space. Remember that in Confluence page titles are unique inside one space. If you use a title of an already existing page, the backend will attempt to edit it and replace its content with your project.

Example config for this situation is:

```yaml
backend_config:
  confluence:
    host: https://my_confluence_server.org
    login: user
    password: pass
    title: My unique title
    space_key: "~user"
```

Now if you change the title in your config, confluence will *create a new page with the new title*, leaving the old one intact.

If you want to change the title of your page, the answer is in the following section.

## Updating pages

Generally to update the page contents you may use the same config you used to create it (see previous section). If the page with specified title exists, it will be updated.

Also, you can just specify the id of an existing page. After build its contents will be updated.

```yaml
backend_config:
  confluence:
    host: https://my_confluence_server.org
    login: user
    password: pass
    id: 124443
```

This is also *the only* way to edit a page title. If `title` param is specified, the backend will attempt to change the page's title to the new one:

```yaml
backend_config:
  confluence:
    host: https://my_confluence_server.org
    login: user
    password: pass
    id: 124443
    title: New unique title
```

## Updating part of a page

Confluence backend can also upload an article into the middle of a Confluence page, leaving all the rest of it intact. To do this you need to add an *Anchor* into your page in the place where you want Foliant content to appear.

1. Go to Confluence web interface and open the article.
2. Go to Edit mode.
3. Put the cursor in the position where you want your Foliant content to be inserted and start typing `{anchor` to open the macros menu and locate the Anchor macro.
4. Add an anchor with the name `foliant`.
5. Save the page.

Now if you upload content into this page (see two previous sections), Confluence backend will leave all text which was before and after the anchor intact, and add your Foliant content in the middle.

You can also add two anchors: `foliant_start` and `foliant_end`. In this case all text between these anchors will be replaced by your Foliant content.

## Inserting raw confluence tags

If you want to supplement your page with confluence macros or any other storage-specific html, you may do it by wrapping them in the `<raw_confluence></raw_confluence>` tag.

For example, if you wish to add a table of contents into the middle of the document for some reason, you can do something like this:

```html
Lorem ipsum dolor sit amet, consectetur adipisicing elit. Odit dolorem nulla quam doloribus delectus voluptate.

<raw_confluence><ac:structured-macro ac:macro-id="1" ac:name="toc" ac:schema-version="1"/></raw_confluence>

Lorem ipsum dolor sit amet, consectetur adipisicing elit. Officiis, laboriosam cumque soluta sequi blanditiis, voluptatibus quaerat similique nihil debitis repellendus.
```
