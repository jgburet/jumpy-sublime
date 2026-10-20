import collections
import json
import os
import random
import string
import sublime
import sublime_plugin


MODE_PHANTOM = "phantom"
MODE_EDIT = "edit"

ACTION_JUMP = "jump"
ACTION_ADD_CURSOR = "add_cursor"
ACTION_SELECT = "select"

REGIONS_KEY = "jumpy"

# Color used when jumpy.label_color is not set, as named by the color scheme.
THEME_LABEL_COLOR = "purplish"
LABEL_SCOPE = "jumpy.label"

# Next to the user's settings rather than in the package, which may be installed as a
# read-only .sublime-package.
GENERATED_COLOR_SCHEMES_DIR = os.path.join("User", "Jumpy")

# Buffers currently holding labels, keyed by buffer id, so they can be restored
# before the user saves or closes them.
labelled_buffers = {}

# Running commands keyed by window id, so focusing a view can end them.
sessions = {}

# Per view id, the selection right after Jumpy's last action in the view, as a set of
# (a, b) pairs, and the point it placed, to find the region a selection starts from.
placements = {}


class JumpyCommand(sublime_plugin.WindowCommand):
	def __init__(self, window):
		super().__init__(window)

		self.anchors = None
		self.renderers = None
		self.action = None
		self.selections = None
		self.origin = None


	def run(self, action=ACTION_JUMP):
		if self.anchors is not None: self.stop()
		else: self.start(action)


	def start(self, action):
		if action not in (ACTION_JUMP, ACTION_ADD_CURSOR, ACTION_SELECT):
			print('Jumpy: unknown action "{}", falling back to "{}"'.format(action, ACTION_JUMP))
			action = ACTION_JUMP

		active_view = self.window.active_view()
		views = get_visible_views(self.window)
		origin = None
		if action == ACTION_SELECT:
			# A selection cannot span views: only the active one gets labels.
			views = [view for view in views if view == active_view]
			origin = find_selection_origin(active_view) if views else None
			if origin is None:
				sublime.status_message('Jumpy: no single new cursor to select from')
				return

		clones_by_buffer = {}
		# A target visible in several clones jumps to the first one: the active view
		# comes first so that the cursor stays in it.
		for view in sorted(views, key=lambda view: view != active_view):
			clones_by_buffer.setdefault(view.buffer_id(), []).append(view)

		# Clones get the same labels whatever the mode, as a buffer can hold only one
		# label per target in edit mode.
		targets_by_renderer = [
			(create_renderer(clones), find_buffer_targets(clones))
			for clones in clones_by_buffer.values()
		]

		anchors = create_anchors(targets_by_renderer)
		if not anchors:
			sublime.status_message('Jumpy: nothing to jump to')
			return

		self.anchors = anchors
		self.renderers = [renderer for (renderer, targets) in targets_by_renderer]
		self.action = action
		self.origin = origin
		# Taken before labels are written: removing them with an undo restores the
		# selection of the view they were written in, but not the one of its clones.
		self.selections = {view.id(): list(view.sel()) for view in views}
		self.refresh("")

		sessions[self.window.id()] = self
		self.window.show_input_panel("", "", self._on_sent, self._on_changed, self._on_closed)


	def stop(self):
		# Hiding the panel calls _on_closed, which calls stop() again.
		if self.anchors is None: return

		for renderer in self.renderers:
			renderer.clear()
		self.anchors = None
		self.renderers = None
		self.action = None
		self.selections = None
		self.origin = None
		sessions.pop(self.window.id(), None)

		if self.window.active_panel() == 'input':
			self.window.run_command("hide_panel")


	def refresh(self, value):
		for renderer in self.renderers:
			renderer.show([
				anchor for label, anchor in self.anchors.items()
				if anchor.renderer is renderer and label.startswith(value)
			])


	def jump(self, anchor):
		action = self.action
		selection = self.selections[anchor.view.id()]
		origin = self.origin
		# Labels must be removed first: in edit mode they may have shifted the target.
		self.stop()
		goto(self.window, anchor.view, anchor.target.begin(), action, selection, origin)


	def _on_sent(self, value):
		anchor = self.anchors.get(value) if self.anchors is not None else None
		if anchor is not None: self.jump(anchor)
		else: self.stop()


	def _on_closed(self):
		self.stop()


	def _on_changed(self, value):
		if self.anchors is None: return

		# Labels are prefix-free, so an exact match is the only remaining candidate.
		anchor = self.anchors.get(value)
		if anchor is not None:
			self.jump(anchor)
			return

		if not any(label.startswith(value) for label in self.anchors):
			self.stop()
			return

		self.refresh(value)


class JumpyLabelBufferCommand(sublime_plugin.TextCommand):
	"""
	Writes labels over the buffer in a single command, so a single undo restores it.
	"""

	def run(self, edit, replacements):
		carets = [region.b for region in self.view.sel()]

		# Replacing from the end keeps the offsets of the earlier replacements valid.
		for (begin, end, label) in reversed(replacements):
			self.view.replace(edit, sublime.Region(begin, end), label)

		# Sublime extends a caret over the text inserted at its position, and the selection
		# color hides the labels' one: selections are reduced to carets, placed before the
		# labels. The undo restoring the buffer restores the original selection as well.
		def move(point):
			return point + sum(
				len(label) - (end - begin)
				for (begin, end, label) in replacements
				if begin < point and end <= point
			)

		self.view.sel().clear()
		for caret in carets:
			self.view.sel().add(move(caret))


class JumpyRestoreEventListener(sublime_plugin.EventListener):
	def on_pre_save(self, view):
		restore_buffer(view)


	def on_pre_close(self, view):
		restore_buffer(view)
		placements.pop(view.id(), None)


	def on_activated(self, view):
		# Focusing a view while labels are displayed (e.g. clicking in it) would let
		# the user edit a buffer that holds labels, which then cannot be undone safely.
		# Every session is stopped, as the buffer may be labelled from another window.
		if view.settings().get('is_widget'): return
		stop_all_sessions()


def plugin_unloaded():
	# The module state is lost on reload: labels left in buffers could no longer be removed.
	stop_all_sessions()


def stop_all_sessions():
	for session in list(sessions.values()):
		session.stop()


def restore_buffer(view):
	labels = labelled_buffers.get(view.buffer_id())
	if labels is not None: labels.clear()


def get_default(key):
	return sublime.load_settings('Jumpy.sublime-settings').get(key)


def get_setting(view, key):
	"""
	View settings come first so that Preferences and syntax specific settings can
	override Jumpy.sublime-settings, which holds the defaults.
	"""

	return view.settings().get(key, get_default(key))


def get_label_color():
	"""
	Read from global settings only: each color scheme gets a single rule for LABEL_SCOPE,
	so the color cannot vary between views.
	"""

	key = 'jumpy.label_color'
	return sublime.load_settings('Preferences.sublime-settings').get(key, get_default(key))


def get_label_scope():
	return LABEL_SCOPE if get_label_color() else 'region.' + THEME_LABEL_COLOR


def sync_label_color(views):
	color = get_label_color()
	if not color:
		# Only empties the files already generated, without generating new ones.
		sync_color_schemes([], [])
		return

	color_schemes = set(c for view in views for c in get_color_schemes(view))
	sync_color_schemes(color_schemes, [{'scope': LABEL_SCOPE, 'background': color}])


def get_color_schemes(view):
	settings = view.settings()
	color_scheme = settings.get('color_scheme')
	if color_scheme == 'auto':
		return [s for s in (settings.get('light_color_scheme'), settings.get('dark_color_scheme')) if s]
	return [color_scheme] if color_scheme else []


def sync_color_schemes(color_schemes, rules):
	"""
	add_regions() only colors through scopes, so the color gets a scope through a rule
	in a file that Sublime merges with the color scheme of the same name. Merging goes
	by file name, hence one file per color scheme the user has worked with, all kept
	up to date with the current color.
	The files are emptied rather than deleted when no color is set: Sublime fails to
	reload a color scheme, and falls back to a blank one, when a file merged into it
	disappears.
	Sublime reloads a color scheme asynchronously: labels displayed right after its
	file is written may not be colored yet.
	"""

	extension = '.sublime-color-scheme'
	directory = os.path.join(sublime.packages_path(), GENERATED_COLOR_SCHEMES_DIR)
	# Other files may land in the directory (e.g. .DS_Store) and must be left alone.
	names = set(n for n in os.listdir(directory) if n.endswith(extension)) if os.path.isdir(directory) else set()
	names.update(os.path.splitext(os.path.basename(c))[0] + extension for c in color_schemes)

	content = {'rules': rules}
	for name in names:
		path = os.path.join(directory, name)
		try:
			with open(path) as f:
				# Rewriting an unchanged file would still make Sublime reload the color scheme.
				if json.load(f) == content: continue
		except (OSError, ValueError):
			pass

		os.makedirs(directory, exist_ok=True)
		with open(path, 'w') as f:
			json.dump(content, f, indent='\t')


def get_mode(view):
	mode = get_setting(view, 'jumpy.mode')
	if mode not in (MODE_PHANTOM, MODE_EDIT):
		print('Jumpy: unknown jumpy.mode "{}", falling back to "{}"'.format(mode, MODE_PHANTOM))
		return MODE_PHANTOM
	return mode


def create_renderer(clones):
	"""
	The mode of the first clone applies to all of them: labels written in the buffer
	would also show in the clones displaying phantoms.
	"""

	if get_mode(clones[0]) == MODE_EDIT: return BufferLabels(clones[0])
	return PhantomLabels(clones[0])


def get_visible_views(window):
	# A group without tabs may still return a placeholder view that window.views() does
	# not list: labelling it would turn it into a new tab.
	tab_ids = set(view.id() for view in window.views())

	views = []
	for group_id in range(window.num_groups()):
		view = window.active_view_in_group(group_id)
		if view is not None and view.id() in tab_ids:
			views.append(view)
	return views


def find_targets(view):
	region = view.visible_region()
	regex = get_setting(view, 'jumpy.regex')
	selector = get_setting(view, 'jumpy.selector')

	targets = []
	cursor = region.begin()
	while cursor <= region.end():
		target = view.find(regex, cursor)
		# find() returns Region(-1, -1) when nothing matches, and may match past the visible region.
		if target.begin() < 0 or target.begin() > region.end(): break

		if not selector or view.match_selector(target.begin(), selector):
			targets.append(target)

		cursor = target.end()
		if target.empty(): cursor += 1
	return targets


def find_buffer_targets(views):
	"""
	Targets visible in any of the views, which show the same buffer, each paired with
	the first of the views showing it.
	Overlapping visible regions may yield the same target twice, or a target starting
	inside another one when a view starts in the middle of a word: only the first one is
	kept, as labels written over overlapping targets would corrupt the buffer.
	"""

	targets = sorted(
		((view, target) for view in views for target in find_targets(view)),
		key=lambda view_target: view_target[1].begin(),
	)

	merged = []
	for (view, target) in targets:
		if merged:
			previous = merged[-1][1]
			if target.begin() == previous.begin() or target.begin() < previous.end(): continue
		merged.append((view, target))
	return merged


def get_clones(view):
	"""
	Views of the view's buffer in every window, the view included: the text is shared
	by the buffer, but regions are drawn per view.
	Buffer.views() would do, but it does not exist in Sublime Text 3.
	"""

	return [
		clone
		for window in sublime.windows() for clone in window.views()
		if clone.buffer_id() == view.buffer_id()
	]


def get_rooms(view, targets):
	"""
	Number of characters a label can overwrite at each target: up to the next target,
	a tab or the end of the line. Tabs are excluded because overwriting them changes
	the alignment of what follows.
	Also tells whether the room is bounded by the end of the line, in which case a
	longer label only extends the line and shifts nothing.
	"""

	rooms = []
	for i, target in enumerate(targets):
		line_end = view.line(target.begin()).end()
		limit = line_end
		if i + 1 < len(targets):
			limit = min(limit, targets[i + 1].begin())
		text = view.substr(sublime.Region(target.begin(), limit))
		tab = text.find('\t')
		if tab >= 0:
			rooms.append((tab, False))
		else:
			rooms.append((len(text), limit == line_end))
	return rooms


def create_anchors(targets_by_renderer):
	candidates = []
	for (renderer, targets) in targets_by_renderer:
		regions = [target for (view, target) in targets]
		for (view, target), (room, at_line_end) in zip(targets, get_rooms(renderer.view, regions)):
			candidates.append((renderer, view, target, room, at_line_end))

	# Shortest labels go to the most cramped targets, where a longer label would shift the text.
	candidates.sort(key=lambda candidate: float('inf') if candidate[4] else candidate[3])
	labels = make_labels(len(candidates), random.sample(string.ascii_lowercase, 26))

	return {
		label: Anchor(label, renderer, view, target, room)
		for label, (renderer, view, target, room, at_line_end) in zip(labels, candidates)
	}


def make_labels(count, alphabet):
	"""
	Returns `count` prefix-free labels of at least 2 characters, sorted by length and
	keeping them as short as possible.
	Prefix-freedom lets a label be selected as soon as it is fully typed.
	Single-character labels are avoided: they are too easily mistaken for the text.
	"""

	labels = [c1 + c2 for c1 in alphabet for c2 in alphabet]
	while len(labels) < count:
		# The last shortest label sits right before the longer ones, so expanding it
		# and appending its children keeps the list sorted by length.
		shortest = len(labels[0])
		index = max(i for i, label in enumerate(labels) if len(label) == shortest)
		prefix = labels.pop(index)
		labels.extend(prefix + c for c in alphabet)
	return labels[:count]


def find_selection_origin(view):
	"""
	Region a selection starts from: the only region added since Jumpy's last action in
	the view, or else the region whose end Jumpy placed, so that consecutive selections
	extend the same region. None when several regions were added, or when none was and
	that region is gone (e.g. dropped by escape).
	Sublime keeps selections sorted by position, not by creation order: comparing them
	with the previous one is the only way to tell which is new. Regions are compared by
	position, so typing or moving the cursors makes them all new.
	"""

	(previous, point) = placements.get(view.id(), (set(), None))
	regions = list(view.sel())

	added = [region for region in regions if (region.a, region.b) not in previous]
	if len(added) == 1: return added[0]
	if added: return None
	return next((region for region in regions if region.b == point), None)


def goto(window, view, point, action, selection, origin):
	"""
	`selection` is the view's selection when the labels were displayed, and `origin`
	the region of it a selection starts from.
	"""

	regions = list(selection)
	if action == ACTION_ADD_CURSOR:
		regions.append(sublime.Region(point))
	elif action == ACTION_SELECT:
		regions[regions.index(origin)] = sublime.Region(origin.a, point)
	else:
		regions = [sublime.Region(point)]

	window.focus_view(view)
	view.sel().clear()
	view.sel().add_all(regions)
	placements[view.id()] = (set((region.a, region.b) for region in view.sel()), point)


def get_html_for_phantom(label_css, label):
	return '''
		<body id="jumpy">
		<style>
			#jumpy .label {''' + label_css + '''}
		</style>
		<div class="label">''' + label + '''</div>
		</body>
	'''


class PhantomLabels:
	"""
	Phantoms belong to the buffer and show in all of its clones: a single phantom set
	draws the labels of the targets visible in any of them.
	"""

	def __init__(self, view):
		self.view = view
		self.phantom_set = sublime.PhantomSet(view, REGIONS_KEY)
		# label_css comes last so that it can override the background color.
		self.label_css = 'background-color: {}; {}'.format(
			get_label_color() or 'var(--{})'.format(THEME_LABEL_COLOR),
			get_setting(view, 'jumpy.label_css'),
		)


	def show(self, anchors):
		self.phantom_set.update([
			sublime.Phantom(anchor.target, get_html_for_phantom(self.label_css, anchor.label), sublime.LAYOUT_INLINE)
			for anchor in anchors
		])


	def clear(self):
		self.phantom_set.update([])


class BufferLabels:
	"""
	Displays labels by writing them over the buffer, then restores it with undo.
	Undo, unlike writing the original text back, leaves both the undo history and
	the dirty state as they were.
	The redo history is not preserved: writing the labels discards it, and a redo
	right after restoring the buffer writes the labels back, untracked.
	"""

	def __init__(self, view):
		self.view = view
		self.label_scope = get_label_scope()
		sync_label_color(get_clones(view))
		# Change count right after the labels were written, None when the buffer holds no labels.
		self.change_count = None
		# Views the label regions were drawn in.
		self.clones = []


	def show(self, anchors):
		self.clear()
		# The view may have been closed during the session, its buffer restored on close.
		if not anchors or not self.view.is_valid(): return

		replacements = []
		regions = []
		shift = 0
		for anchor in sorted(anchors, key=lambda anchor: anchor.target.begin()):
			begin = anchor.target.begin()
			end = begin + min(anchor.room, len(anchor.label))
			replacements.append((begin, end, anchor.label))
			regions.append(sublime.Region(begin + shift, begin + shift + len(anchor.label)))
			shift += len(anchor.label) - (end - begin)

		self.run_writable('jumpy_label_buffer', {'replacements': replacements})
		self.change_count = self.view.change_count()
		labelled_buffers[self.view.buffer_id()] = self
		self.clones = get_clones(self.view)
		for clone in self.clones:
			clone.add_regions(REGIONS_KEY, regions, self.label_scope, '', sublime.DRAW_NO_OUTLINE)


	def clear(self):
		if self.change_count is None: return

		for clone in self.clones:
			clone.erase_regions(REGIONS_KEY)
		self.clones = []
		# Something else edited the buffer meanwhile (reload from disk, another plugin):
		# undoing would revert that edit instead of the labels.
		if self.view.change_count() == self.change_count:
			self.run_writable('undo')
		else:
			# A dialog rather than a console message: the labels may be about to be saved to disk.
			sublime.error_message('Jumpy: the buffer changed while labels were displayed, they were not removed and must be undone manually:\n{}'.format(self.view.file_name() or self.view.name()))

		self.change_count = None
		labelled_buffers.pop(self.view.buffer_id(), None)


	def run_writable(self, command, args=None):
		read_only = self.view.is_read_only()
		self.view.set_read_only(False)
		try:
			self.view.run_command(command, args)
		finally:
			self.view.set_read_only(read_only)


Anchor = collections.namedtuple('Anchor', 'label renderer view target room')
