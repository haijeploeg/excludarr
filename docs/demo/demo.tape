# Records docs/demo/demo.gif. See Dockerfile in this directory for how to run it.
Output demo.gif

Set Shell bash
Set FontSize 15
Set Width 1200
Set Height 900
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Hide
Type "python fake_radarr.py & sleep 1; rm -f excludarr.db; export EXCLUDARR_CONFIG=excludarr.yml PS1='$ '; clear"
Enter
Sleep 2s
Show

Type "cat excludarr.yml"
Sleep 300ms
Enter
Sleep 5s

Type "excludarr config validate"
Sleep 300ms
Enter
Sleep 3s

Type "clear; excludarr run -y"
Sleep 300ms
Enter
Sleep 9s

Type "clear; excludarr queue"
Sleep 300ms
Enter
Sleep 6s

Hide
Type "rm -f excludarr.db"
Enter
