# 0.6.0

- 

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