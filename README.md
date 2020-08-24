# jumpy-sublime
An equivalent of [Atom's Jumpy package](https://github.com/DavidLGoldberg/jumpy), for Sublime Text.

![Demo of Jumpy](images/jumpy-in-action.gif)

## Installation
Jumpy is not yet referenced in Sublime's Package Control Repository. [It's in its way though.](https://github.com/wbond/package_control_channel/pull/8005)  
  
In the mean time, you can use it by putting it in your local packages folder.
On MacOS this should work:
```bash
git clone "https://github.com/jgburet/jumpy-sublime.git" \
	"~/Library/Application Support/Sublime Text 3/Packages/Jumpy"
```

Jumpy does not come with predefined bindings so you'll need to define yours.  
Go to `Preferences > Key Bindings`. Complete the file with this line:
```json
[
    { "keys": ["shift+enter"], "command": "jumpy" }
]
```

## Style
You can customize how labels look like by editing your color scheme:
```html
#jumpy .label {
	<your css>
}
```
