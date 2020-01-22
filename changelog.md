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