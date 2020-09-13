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
#### `Regions` selection
Putting labels in front of words is nice, but often I'd like to jump at end of lines, on opening brackets or emptylines. This would easily be feasable if the `regions` were selected using a regex rather than ST's used built-in.
#### Multi cursors
#### Select text to other label

## TOFIX
#### Word detection
The last word never receives a label. The matching is not done using a regex but a ST built-in. The `region` this give me is always too big. When trying to locate the next `region`, I might shift the detection cursor somehow too far.  
To fix it, I should use a basic regex like `/[a-z-_]{2,}/i`.
