# 0.6.21

- Fixed unescaped hash in links which are not returned back after processing.
- Removed extra whitespace appeared after some processed links at the end of sentence in Confluence.

# 0.6.20

- Support for Confluence Cloud option to remove HTML formatting.
- Page URL is now taken from the properties.
- Article change is now detected by article body and title hash, stored in page properties.

# 0.6.19

- New utils module.

# 0.6.18

- Fix: external images didn't work.

# 0.6.17

- Fix: parent_id param didn't work.

# 0.6.16

- New: attaching arbitrary files with help of `attachments` parameter.
- New: supply attachments implicitly using `ac:image` tag, without mentioning them in `attachments` parameter.
- Attachments and images which were referenced several times on a page will now only be uploaded once.
- Allow `!path`, `!project_path` modifiers inside `ac:attachment` param for `ac:link`, `ac:image`.

# 0.6.15

- New: \[experimental\] `raw_confluence` tags are now not necessary for `ac:...` tags, they are escaped automatically.
- New: supply images with additional parameters using `ac:image` tag.
- New: `verify_ssl` parameter.

# 0.6.14

- Add code blocks processing for Confluence preprocessor.

# 0.6.13

- Fix: cache dir for preprocessor was not created

# 0.6.12

- New: option to store passwords in passfile.
- New: nohead option to crop first title from the page.
- Fix: better error reporting after updated atlassian-python-api package.
- New: if you specified only `space_key` param in metadata and no `title`, section heading will be used as title.
- Fix: if hierarchy is created on the test run, missing parents by title are now ignored

# 0.6.11

- Fix: XML error in code block conversion.

# 0.6.10

- Disabled tabbed code blocks conversion because of conflicts.

# 0.6.9

- Introducing import from confluence into Foliant with `confluence` tag
- Fix: solved conflicts between inline comments and macros (including anchors)
- Fix: backend crashed if new page content was empty
- Markdown code blocks are now converted into code-block macros
- Markdown task lists are now converted into task-list macros
- New `test_run` option

# 0.6.8

- Now foliant-anchors are always added even for new pages

# 0.6.7

- Fix another conflict with escapecode

# 0.6.6

- Support meta 1.3
- Now foliant-anchors are always added around uploaded content
- Anchors are now case insensitive

# 0.6.5

- Fix: build crashed when several resolved inline comments referred to same string

# 0.6.4

- Support meta 1.2. Now you can publish sections to confluence.

# 0.6.3

- Remove resolved inline comments as they mix up with unresolved.

# 0.6.2

- Added `parent_title` parameter.
- Fix: images were not uploaded for new pages.

# 0.6.0

- Now content is put in place of `foliant` anchor or instead of `foliant_start`...`foliant_end` anchors on the target page. If no anchors on page — content replaces the whole body.
- New modes (backwards compatibility is broken!).
- Now following files are available for debug in cache dir: 1. markdown before conversion to html. 2. Converted to HTML. 3. Final XHTML source which is uploaded to confluence.
- Working (but far from perfect) detection if file was changed.
- Only upload changed attachments.
- Updating attachments instead of deleting and uploading again.

# 0.5.2

- Completely rewrite restoring inline comments feature.
- Add `restore_comments` and `resolve_if_changed` emergency options.
- Allow insert raw confluence code (macros, etc) inside `<raw_confluence>` tag.

# 0.4.1

- Fix: conflict with escape_code

# 0.4.0

- Fix: attachments were not uploaded for nonexistent pages
- Change confluence api wrapper to atlassian-python-api
- Rename backend to confluence
- Better error reporting

# 0.3.0

- Fix bug with images.
- Add multiple modes and mode parameter.
- Add toc parameter to automatically insert toc.
- Fix: upload attachments before text update (this caused images to disappear after manually editing).

# 0.2.0

- Allow to input login and/or password during build
- Added `pandoc_path` option
- Better logging and error catching

# 0.1.0

- Initial release.
