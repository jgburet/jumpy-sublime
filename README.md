# jumpy-sublime
An equivalent of [Atom's Jumpy package](https://github.com/DavidLGoldberg/jumpy), for Sublime Text.

![Demo of Jumpy](images/jumpy-in-action.gif)

## Installation

### Step 1: download package
#### Option 1: using Package Control
Open the Command Palette:  
- on PC: `shift+control+P`  
- on Mac: `shift+command+P`  

Select `Package Control: Install Package`.  

Select `Jumpy`.

#### Option 2: using GIT
```bash
git clone "https://github.com/jgburet/jumpy-sublime.git" \
	"~/Library/Application Support/Sublime Text 3/Packages/Jumpy" # <-- MacOS destination
```

### Step 2: configure bindings
Jumpy does not come with predefined bindings so you'll need to define yours.  
Go to `Preferences > Key Bindings`. Complete the file with this line:
```json
[
    { "keys": ["shift+enter"], "command": "jumpy" }
]
```

## Customization
You can customize how labels look like by editing your color scheme:
```html
#jumpy .label {
	<your css>
}
```

## TODO
#### Improve labels
Right now, labels are displayed using `phantoms`. When displayed, they shift your text. It's annoying.  
I'd prefer to edit the `buffer` but this complexifies A LOT how the package works, having to orchestrate more commands.  
Also, there's that to deal with https://github.com/sublimehq/sublime_text/issues/817#issuecomment-95211154.

#### Multi cursors
Keep current cursors and add new one on selected label. 

#### Select text between cursor and label
