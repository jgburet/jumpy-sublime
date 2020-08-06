import random
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

		self.anchors = {}
		self.phantom_sets = []
		for view in get_visible_views(self.window):
			phantom_set = sublime.PhantomSet(view)

			phantoms = []
			for word in xget_words_in_region(view, view.visible_region()):
				label = labels.__next__()
				phantom = sublime.Phantom(word, get_html_for_phantom(label), sublime.LAYOUT_INLINE)

				phantoms.append(phantom)
				self.anchors.update({ label: (view, word, phantom) })

			phantom_set.update(phantoms)
			self.phantom_sets.append(phantom_set)

		self.window.show_input_panel("", "", self._on_sent, self._on_changed, self._on_closed)


	def stop(self):
		self.anchors = None
		self.phantom_sets = None

		if self.window.active_panel() == 'input':
			self.window.run_command("hide_panel")

		self.is_running = False


	def _on_sent(self, value):
		self.anchors = None
		self.phantom_sets = None

		self.is_running = False


	def _on_closed(self):
		self.anchors = None
		self.phantom_sets = None

		self.is_running = False


	def _on_changed(self, value):
		if len(value) < 2: return

		destination = None
		if value in self.anchors:
			destination = self.anchors[value]

		self.anchors = None
		self.phantom_sets = None

		self.window.run_command("hide_panel")

		if destination:
			(view, word, _) = destination
			self.window.focus_view(view)
			view.sel().clear()
			view.sel().add(word.begin())
			view.show(word.begin())

		self.is_running = False


def abc():
	for c in random.sample(string.ascii_lowercase, 26):
		yield c


def xget_labels():
	for c1 in abc():
		for c2 in abc():
			yield c1 + c2


def get_visible_views(window):
	views = []
	for group_id in range(window.num_groups()):
		view = window.active_view_in_group(group_id)
		views.append(view)
	return views


def xget_words_in_region(view, region):
	mask = sublime.CLASS_WORD_START

	cursor = view.find_by_class(region.begin(), True, mask)
	while cursor < region.end():
		word = view.expand_by_class(cursor, mask)
		yield word
		cursor = view.find_by_class(word.end() - 1, True, mask)


def get_html_for_phantom(label):
	color = "purple"
	font_size = 0.7

	return '''
		<body id="jumpy-phantom">
		<style>
			html {
				background-color: ''' + color + ''';
				font-size: ''' + str(font_size) + '''rem;
			}
		</style>
		''' + label + '''
		</body>
	'''
