
# Confluence backend for Foliant

[![](https://img.shields.io/pypi/v/foliantcontrib.confluence.svg)](https://pypi.org/project/foliantcontrib.confluence/) [![](https://img.shields.io/github/v/tag/foliant-docs/foliantcontrib.confluence.svg?label=GitHub)](https://github.com/foliant-docs/foliantcontrib.confluence)

![Confluence page built with Foliant](https://raw.githubusercontent.com/foliant-docs/foliantcontrib.confluence/master/img/confluence.png)

Confluence backend generates confluence articles and uploads them on your confluence server. It can create and edit pages in Confluence with content based on your Foliant project.

It also has a feature of restoring the user inline comments, added for the article, even after the commented fragment was changed.

This backend adds the `confluence` target for your Foliant `make` command.

## Installation

```bash
$ pip install foliantcontrib.confluence
```

> The backend requires [Pandoc](https://pandoc.org/) to be installed on your system. Pandoc is needed to convert Markdown into HTML.

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

You have to set up the correct config for this backend to work properly.

Specify all options in `backend_config.confluence` section:

```yaml
backend_config:
  confluence:
    passfile: confluence_secrets.yml
    host: 'https://my_confluence_server.org'
    login: user
    password: user_password
    id: 124443
    title: Title of the page
    space_key: "~user"
    parent_id: 124442
    parent_title: Parent
    test_run: false
    notify_watchers: false
    toc: false
    nohead: false
    restore_comments: true
    resolve_if_changed: false
    pandoc_path: pandoc
    verify_ssl: true
    attachments:
        - license.txt
        - project.pdf
    codeblocks:
        ...
```

`passfile`
:   Path to YAML-file holding credentials. See details in **Supplying Credentials** section. Default: `confluence_secrets.yml`

`host`
:   **Required** Host of your confluence server.

`login`
:   Login of the user who has permissions to create and update pages. If login is not supplied, it will be prompted during the build.

`password`
:   Password of the user. If the password is not supplied, it will be prompted during the build.

`id`
:   ID of the page where the content will be uploaded. *Only for already existing pages*

`title`
:   Title of the page to be created or updated.

> Remember that page titles in one space must be unique.

`space_key`
:   The space key where the page(s) will be created/edited. *Only for not yet existing pages*.

`parent_id`
:   ID of the parent page under which the new one(s) should be created. *Only for not yet existing pages*.

`parent_title`
:   Another way to define the parent of the page. Lower priority than `paren_di`. Title of the parent page under which the new one(s) should be created. The parent should exist under the space_key specified. *Only for not yet existing pages*.

`test_run`
:   If this option is true, Foliant will prepare the files for uploading to Confluence, but won't actually upload them. Use this option for testing your content before upload. The prepared files can be found in `.confluencecache/debug` folder. Default: `false`

`notify_watchers`
:   If `true` — watchers will be notified that the page has changed. Default: `false`

`toc`
:   Set to `true` to add a table of contents to the beginning of the document. Default: `false`

`nohead`
:   If set to `true`, first title will be removed from the page. Use it if you are experiencing duplicate titles. Default: `false`

`restore_comments`
:   Attempt to restore inline comments near the same places after updating the page. Default: `true`

`resolve_if_changed`
:   Delete inline comment from the source if the commented text was changed. This will automatically mark the comment as resolved. Default: `false`

`pandoc_path`
:   Path to Pandoc binary (Pandoc is used to convert Markdown into HTML).

`verify_ssl`
:   If `false`, SSL verification will be turned off. Sometimes when dealing with Confluence servers in Intranets it's easier to turn this option off rather than fight with admins. Not recommended to turn off for public servers in production. Default: `true`

`attachments`
:   List of files (relative to project root) which should be attached to the Confluence page.

`codeblocks`
:   Configuration for converting Markdown code blocks into code-block macros. See details in **Code blocks processing** sections.

## User's guide

### Uploading articles

By default, if you specify `id` or `space_key` and `title` in foliant.yml, the whole project will be built and uploaded to this page.

If you wish to upload separate chapters into separate articles, you need to specify the respective `id` or `space_key` and `title` in *meta section* of the chapter.

Meta section is a YAML-formatted field-value section in the beginning of the document, which is defined like this:

```yaml
---
field: value
field2: value
---

Your chapter md-content
```

or like this:

```html
<meta
    field="value"
    field2="value">
</meta>

Your chapter md-content
```

> The result of the above examples will be exactly the same. Just remember that first syntax, with three dashes --- will only work if it is in the beginning of the document. For all other cases use the meta-tag syntax.

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
> Both modes work together. If you specify the `id1` in foliant.yml and `id2` in chapter's meta — the whole project will be uploaded to the page with `id1`, and the specific chapter will also be uploaded to the page with `id2`.

> **Notice**
> You can omit `title` param in metadata. In this case section heading will be used as a title.


If you want to upload just a part of the chapter, specify meta tag under the heading, which you want to upload, like this:

```html
# My document

Lorem ipsum dolor sit amet, consectetur adipisicing elit. Explicabo quod omnis ipsam necessitatibus, enim voluptatibus.

## Components

<meta
    confluence="
        title: 'System components'
        space_key: '~user'
    ">
</meta>

Lorem ipsum dolor sit amet, consectetur adipisicing elit. Vel, atque!
...
```

In this example, only the **Components** section with all its content will be uploaded to Confluence. The **My document** heading will be ignored.

### Creating pages

If you want a new page to be created for content in your Foliant project, just supply in foliant.yml the space key and a title that does not yet exist in this space. Remember that in Confluence page titles are unique inside one space. If you use a title of an already existing page, the backend will attempt to edit it and replace its content with your project.

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

### Updating pages

Generally to update the page contents you may use the same config you used to create it (see the previous section). If the page with a specified title exists, it will be updated.

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

### Updating part of a page

Confluence backend can also upload an article into the middle of a Confluence page, leaving all the rest of it intact. To do this you need to add an *Anchor* into your page in the place where you want Foliant content to appear.

1. Go to Confluence web interface and open the article.
2. Go to Edit mode.
3. Put the cursor in the position where you want your Foliant content to be inserted and start typing `{anchor` to open the macros menu and locate the Anchor macro.
4. Add an anchor with the name `foliant`.
5. Save the page.

Now if you upload content into this page (see two previous sections), Confluence backend will leave all text which was before and after the anchor intact, and add your Foliant content in the middle.

You can also add two anchors: `foliant_start` and `foliant_end`. In this case, all text between these anchors will be replaced by your Foliant content.

> **Known issue:** right now this mode doesn't work with *layout sections*. If you are using sections, whole content will be overwritten.

### Inserting raw confluence tags

If you want to supplement your page with confluence macros or any other storage-specific HTML, you may do it by wrapping them in the `<raw_confluence></raw_confluence>` tag.

For example, if you wish to add a table of contents into the middle of the document for some reason, you can do something like this:

```html
Lorem ipsum dolor sit amet, consectetur adipisicing elit. Odit dolorem nulla quam doloribus delectus voluptate.

<raw_confluence><ac:structured-macro ac:macro-id="1" ac:name="toc" ac:schema-version="1"/></raw_confluence>

Lorem ipsum dolor sit amet, consectetur adipisicing elit. Officiis, laboriosam cumque soluta sequi blanditiis, voluptatibus quaerat similique nihil debitis repellendus.
```

In version 0.6.15 we've added an experimental feature of automatically escaping `<ac:...></ac:...>` tags for you. So if you want to insert, say, an image with native Confluence tag `ac:image`, you don't have to wrap it in `raw_confluence` tag, but keep in mind following caveats:

- singleton `ac:...` tags are not supported, so `<ac:emoticon ac:name="cross" />` will not work, you will have to provide the closing tag: `<ac:emoticon ac:name="cross"></ac:emoticon>`,
- only `ac:...` tags are escaped right now, other confluence tags like `ri:...` or `at:...` are left as is. If these tags appear inside `ac:...` tag, it's ok. If otherwise, `ac:...` tag appears inside `at:...` or `ri:...` tag, everything will break.

### Attaching files

To attach an arbitrary file to Confluence page simply put path to this file in the `attachments` parameter in foliant.yml or in meta section.

This will just tell Foliant to attach this file to the page, but if you want to reference it in text, use the other approach:

Insert Confluence `ac:link` tag to attachment right inside your Markdown document and put local path to your file in the `ri:filename` parameter like this:

```
Presentation in PDF:

<ac:link>
  <ri:attachment ri:filename="presentation.pdf"/>
</ac:link>
```

In this case Foliant will upload the `presentation.pdf` to the Confluence page and make a link to it in the text. The path in `ri:filename` parameter should be relative to current Markdown file, but you can use `!path`, `!project_path` modifiers to reference images relative to project root.

### Advanced images

Confluence has an `ac:image` tag which allows you to transform and format your attached images:

- resize,
- set alignment,
- add borders,
- etc.

Since version `0.6.15` you have access to all these features. Now instead of plain Markdown-image syntax you can use native Confluence image syntax. Add an `ac:image` tag as if you were editing page source in Confluence interface and use local relative path to the image as if you were inserting Markdown-image.

For example, if you have an image defined like this:

```
![My image](img/picture.png)
```

and you want to resize it to 600px and align to center, replace it with following tag:

```
<ac:image ac:height="600" ac:align="center">
    <ri:attachment ri:filename="img/picture.png" />
</ac:image>
```

As you noticed, you should put path to your image right inside the `ri:filename` param. This path should be relative to current Markdown file, but you can (since 0.6.16) use `!path`, `!project_path` modifiers to reference images relative to project root.

Here's [a link to Confluence docs](https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html#ConfluenceStorageFormat-Images) about `ac:image` tag and all possible options.

If you want to upload an external image, you can also use this approach, just insert that proper `ac:image` tag, no need for `raw_confluence`:

```
External image:


<ac:image>
<ri:url ri:value="http://confluence.atlassian.com/images/logo/confluence_48_trans.png" /></ac:image>
```


### Code blocks processing

Since 0.6.9 backend converts Markdown code blocks into Confluence code-block macros. You can tune the macros appearance by specifying some options in `codeblocks` config section of Confluence backend

```yaml
backend_config:
    confluence:
        codeblocks:  # all are optional
            theme: django
            title: Code example
            linenumbers: false
            collapse: false
```


`theme`
:   Color theme of the code blocks. Should be one of:

* `emacs`,
* `django`,
* `fadetogrey`,
* `midnight`,
* `rdark`,
* `eclipse`,
* `confluence`.

`title`
:   Title of the code block.

`linenumbers`
:   Show line numbers in code blocks. Default: `false`

`collapse`
:   Collapse code blocks into a clickable bar. Default: `false`

Right now Foliant only converts code blocks by backticks/tildes (tabbed code blocks are ignored for now):

~~~
This code block will be converted:

```python
def test2():
    pass
 ```
~~~

```
And this:
~~~
def test3():
    pass
~~~
```

Syntax name, defined after backticks/tildes is converted into its Confluence counterpart. Right now following syntaxes are supported:

* `actionscript`,
* `applescript`,
* `bash`,
* `c`,
* `c`,
* `coldfusion`,
* `cpp`,
* `cs`,
* `css`,
* `delphi`,
* `diff`,
* `erlang`,
* `groovy`,
* `html`,
* `java`,
* `javascript`,
* `js`,
* `perl`,
* `php`,
* `powershell`,
* `python`,
* `xml`,
* `yaml`.

### Supplying Credentials

There are several ways to supply credentials for your confluence server.

**1. In foliant.yml**

The most basic way is just to put credentials in foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        login: user
        password: pass
```

It's not very secure because foliant.yml is usually visible to everybody in your project's git repository.

**2. Omit credentials in config**

A slightly more secure way is to remove password or both login and password from config:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        login: user
```

In this case Foliant will prompt for missing credentials during each build:

```bash
$ foliant make confluence
Parsing config... Done
Applying preprocessor confluence_final... Done
Making confluence...

!!! User input required !!!
Please input password for user:
$
```

**3. Using environment variables**

Foliant 1.0.12 can access environment variables inside config files with `!env` modifier.

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        login: !env CONFLUENCE_USER
        password: !env CONFLUENCE_PASS
```

Now you can add these variables into your command:

```bash
CONFLUENCE_USER=user CONFLUENCE_PASS=pass foliant make confluence
```

Or, if you are using docker:

```bash
docker-compose run --rm -e CONFLUENCE_USER=user -e CONFLUENCE_PASS=pass foliant make confluence
```

**4. Using passfile**

Finally, you can use a passfile. *Passfile* is a yaml-file which holds all your passwords. You can keep it out from git-repository by storing it only on your local machine and production server.

To use passfile, add a `passfile` option to foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        passfile: confluence_secrets.yaml
```

The syntax of the passfile is the following:

```yaml
hostname:
    login: password
```

For example:

```yaml
https://my_confluence_server.org:
    user1: wFwG34uK
    user2: MEUeU3b4
https://another_confluence_server.org:
    admin: adminpass
```

If there are several records for a specified host in passfile (like in the example above), Foliant will pick the first one. If you want specific one of them, add the login parameter to your foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        passfile: confluence_secrets.yaml
        login: user2
```

## Credits

The following wonderful tools and libraries are used in foliantcontrib.confluence:

- [Atlassian Python API wrapper](https://github.com/atlassian-api/atlassian-python-api),
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/),
- [PyParsing](https://github.com/pyparsing/pyparsing),
- [Pandoc](https://pandoc.org/).

# Confluence Preprocessor for Foliant

[![](https://img.shields.io/pypi/v/foliantcontrib.confluence.svg)](https://pypi.org/project/foliantcontrib.confluence/) [![](https://img.shields.io/github/v/tag/foliant-docs/foliantcontrib.confluence.svg?label=GitHub)](https://github.com/foliant-docs/foliantcontrib.confluence)

Confluence preprocessor allows inserting content from Confluence server into your Foliant project.

## Installation

```bash
$ pip install foliantcontrib.confluence
```

## Config

To enable the preprocessor, add `confluence` to `preprocessors` section in the project config:

```yaml
preprocessors:
    - confluence
```

The preprocessor has a number of options:

```yaml
preprocessors:
    - confluence:
        passfile: confluence_secrets.yml
        host: https://my_confluence_server.org
        login: user
        password: !CONFLUENCE_PASS
        space_key: "~user"
        pandoc_path: pandoc
        verify_ssl: true
```

`passfile`
:   Path to YAML-file holding credentials. See details in **Supplying Credentials** section. Default: `confluence_secrets.yml`

`host`
:   **Required** Host of your confluence server. If not stated — it would be taken from Confluence backend config.

`login`
:   Login of the user who has permissions to create and update pages. If login is not supplied, it would be taken from backend config, or prompted during the build.

`password`
:   Password of the user. If password is not supplied, it would be taken from backend config, or prompted during the build.

> It is not secure to store plain text passwords in your config files. We recommend to use [environment variables](https://foliant-docs.github.io/docs/config/#env) to supply passwords

`space_key`
:   The space key where the page titles will be searched for.

`pandoc_path`
:   Path to Pandoc executable (Pandoc is used to convert Confluence content into Markdown).

`verify_ssl`
:   If `false`, SSL verification will be turned off. Sometimes when dealing with Confluence servers in Intranets it's easier to turn this option off rather than fight with admins. Not recommended to turn off for public servers in production. Default: `true`

## Usage

Add a `<confluence></confluence>` tag at the position in the document where the content from Confluence should be inserted. The page is defined by its `id` or `title`. If you are specifying page by title, you will also need to set `space_key` either in tag or in the preprocessor options.

```html
The following content is imported from Confluence:

<confluence id="12345"></confluence>

This is from Confluence too, but determined by page title (space key is defined in preprocessor config):

<confluence title="My Page"></confluence>

Here we are overriding space_key:

<confluence space_key="ANOTHER_SPACE" title="My Page"></confluence>
```

### Supplying Credentials

There are two ways to supply credentials for your confluence server.

**1. In foliant.yml**

The most basic way is just to put credentials in foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        login: user
        password: pass
```

It's not very secure because foliant.yml is usually visible to everybody in your project's git repository.

**2. Using passfile**

Alternatively, you can use a passfile. *Passfile* is a yaml-file which holds all your passwords. You can keep it out from git-repository by storing it only on your local machine and production server.

To use passfile, add a `passfile` option to foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        passfile: confluence_secrets.yaml
```

The syntax of the passfile is the following:

```yaml
hostname:
    login: password
```

For example:

```yaml
https://my_confluence_server.org:
    user1: wFwG34uK
    user2: MEUeU3b4
https://another_confluence_server.org:
    admin: adminpass
```

If there are several records for a specified host in passfile (like in the example above), Foliant will pick the first one. If you want specific one of them, add the login parameter to your foliant.yml:

```yaml
backend_config:
    confluence:
        host: https://my_confluence_server.org
        passfile: confluence_secrets.yaml
        login: user2
```