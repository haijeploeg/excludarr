---
name: Bug report
about: Create a report to help us improve
title: ''
labels: bug
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. The exact command that throws an error
2. The name of the movie or serie that is being processed at the time of the error (if applicable)
3. The settings file used (strip it from sensitive data)

**Expected behavior**
A clear and concise description of what you expected to happen.

**Versions**
1. OS Version: ...
2. Excludarr version: ...
3. Python version: ...

**Debug logging**
To debug the problem further, we need to know exactly what went wrong. Therefor we ask you to run the command in debug mode. You can achieve this by appending the `--debug` flag after the base command `excludarr`. e.g. `excludarr --debug sonarr exclude -a delete -d -e`.

If the output is too long, please paste the output to pastebin or github gist and link it in this issue.

**Additional context**
Add any other context about the problem here.
