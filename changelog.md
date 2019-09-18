# 0.4.2

- Detect if page hadn't changed and don't upload it. Changed pages are marked by "*" in the output.
- s

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