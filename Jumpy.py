import random
from functools import reduce
import string
import sublime
import sublime_plugin


class JumpyCommand(sublime_plugin.WindowCommand):
	def __init__(self, window):
		super().__init__(window)

		self.is_running = False


	def run(self):
		if self.is_running: self.stop()
		else: self.start()


	def start(self):
		self.is_running = True
		labels = xget_labels()

		self.active_views = []
		for view in get_visible_views(self.window):
			anchors = create_anchors(view, labels)
			phantom_set = sublime.PhantomSet(view)

			self.active_views.append(ActiveView(anchors, None, phantom_set, view))

		self.window.show_input_panel("", "", self._on_sent, self._on_changed, self._on_closed)


	def stop(self):
		self.active_views = None

		if self.window.active_panel() == 'input':
			self.window.run_command("hide_panel")

		self.is_running = False


	def _on_sent(self, value):
		"""
		In 99% of the cases, _on_changed will catch the input before we press ENTER.
		However, if we reach 3-chars-length labels (>26^2 labels displayed), we need to make
		the 2-chars-length label selectable.
		That's why we check if the value is among the labels we generated.
		eg: Having "kl" and "klm" displayed, the user will have to press ENTER to validate "kl".
		"""

		target = find_anchor(self.active_views, value)
		if target != None:
			(view, anchor) = target
			self.goto(self.window, view, anchor.word)

		self.active_views = None

		self.is_running = False


	def _on_closed(self):
		self.active_views = None

		self.is_running = False


	def _on_changed(self, value):
		for active_view in self.active_views:
			refresh_active_view(active_view, value)
		phantoms_left = reduce(lambda acc, active_view: acc + active_view.count, self.active_views, 0)

		if phantoms_left == 0:
			self.stop()
			return

		if phantoms_left > 1:
			return

		view, anchor = find_anchor(self.active_views, value)
		goto(self.window, view, anchor.word)
		self.stop()


def abc():
	for c in random.sample(string.ascii_lowercase, 26):
		yield c


def xget_labels():
	for c1 in abc():
		for c2 in abc():
			yield c1 + c2
	for c1s in xget_labels():
		for c2 in abc():
			yield c1s + c2


def get_visible_views(window):
	views = []
	for group_id in range(window.num_groups()):
		view = window.active_view_in_group(group_id)
		views.append(view)
	return views


def create_anchors(view, labels):
	words = xget_words_in_region(view, view.visible_region())

	anchors = {}
	for word in words:
		label = labels.__next__()
		html = get_html_for_phantom(label)
		phantom = sublime.Phantom(word, html, sublime.LAYOUT_INLINE)

		anchors.update({ label: Anchor(label, phantom, word) })

	return anchors


def filter_phantoms(anchors, searched):
	return [anchor.phantom for label, anchor in anchors.items() if searched in label]


def refresh_active_view(active_view, value):
	phantoms = filter_phantoms(active_view.anchors, value)

	active_view.count = len(phantoms[:2]) # we only want to know if there are more than one
	active_view.set = sublime.PhantomSet(active_view.view)
	active_view.set.update(phantoms)


def find_anchor(active_views, value):
	return next(((av.view, av.anchors[value]) for av in active_views if value in av.anchors), None)


def goto(window, view, region):
	window.focus_view(view)
	view.sel().clear()
	view.sel().add(region.begin())


def xget_words_in_region(view, region):
	mask = sublime.CLASS_WORD_START

	cursor = view.find_by_class(region.begin(), True, mask)
	while cursor < region.end():
		word = view.expand_by_class(cursor, mask)
		yield word
		cursor = view.find_by_class(word.end() - 1, True, mask)


def get_html_for_phantom(label):
	return '''
		<body id="jumpy">
		<style>
			#jumpy .label {
				background-color: purple;
				font-size: 0.7rem;
			}
		</style>
		<div class="label">''' + label + '''</div>
		</body>
	'''


class Anchor:
	def __init__(self, label, phantom, word):
		self.label = label
		self.phantom = phantom
		self.word = word


class ActiveView:
	def __init__(self, anchors, count, phantom_set, view):
		self.anchors = anchors
		self.count = count
		self.set = phantom_set
		self.view = view