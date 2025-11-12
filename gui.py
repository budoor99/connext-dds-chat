# gui.py
import tkinter as tk
from tkinter import ttk, font, messagebox
import logging
from typing import Callable, Optional, List
from datetime import datetime

class Handlers:
    join:          Callable[[str, str, Optional[str], Optional[str]], None] = lambda *_: logging.warning("Not implemented")
    update_user:   Callable[[str], None] = lambda *_: logging.warning("Not implemented")
    leave:         Callable[[], None] = lambda *_: logging.warning("Not implemented")
    list_users:    Callable[[], List[str]] = lambda *_: logging.warning("Not implemented")
    send_message:  Callable[[str, str], None] = lambda *_: logging.warning("Not implemented")
    search_history:Callable[[str], None] = lambda *_: logging.warning("Not implemented")

def _now_hms(): return datetime.now().strftime('%H:%M:%S')
def _fmt_ts(ms):
        try:
            return datetime.fromtimestamp(ms/1000.0).strftime('%H:%M:%S')
        except Exception:
            return None

class GuiApp:
    def __init__(self, handlers=Handlers()):
        self.root = tk.Tk()
        self.root.title("Chat App")
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.state_joined = False
        self.handlers = handlers
        self.widgets = _GuiWidgets(self)

    def start(self):
        self.root.mainloop()

    # Called by app:
    def user_joined(self, user, group, name="", last_name=""):
        if not self.state_joined: return
        if not self.widgets.online_users_tree.add_user(user, group, name, last_name): return
        space = " " if (name and last_name) else ""
        fullname = f" ({name}{space}{last_name})" if (name or last_name) else ""
        self.widgets.message_text.append_line(f"[{_now_hms()}] > {user}{fullname} joined on group {group}.")

    def user_left(self, user):
        if not self.state_joined: return
        if not self.widgets.online_users_tree.delete_user(user): return
        self.widgets.message_text.append_line(f"[{_now_hms()}] > {user} dropped.")

    def message_received(self, user, destination, message, timestamp_ms=None):
        dest_str = "you" if destination == self.widgets.user_entry.get() else destination
        ts = _fmt_ts(timestamp_ms) if timestamp_ms else None
        prefix = f"[{ts}] " if ts else ""
        self.widgets.message_text.append_line(f"{prefix}{user} (to {dest_str}): {message}")

    def history_results(self, items):
        if not items:
            self.widgets.message_text.append_line("> No matches.")
            return
        self.widgets.message_text.append_line(f"> Found {len(items)} message(s):")
        for s in items:
            dest = s.toUser if s.toUser else s.toGroup
            self.widgets.message_text.append_line(f"{s.fromUser} (to {dest}): {s.message}")

    # Private UI actions
    def _close(self):
        if self.state_joined:
            self._leave()
        self.root.destroy()

    def _join(self):
        user  = self.widgets.user_entry.get()
        group = self.widgets.group_entry.get()
        if not all((user, group)):
            _ = "username" if not user else "group"
            __ = " and group." if not any((user, group)) else "."
            messagebox.showerror(title="Error", message=f"Please insert a {_}{__}")
            return

        self.state_joined = True
        kwargs = {ename: entry.get() for ename, entry in self.widgets.entry_widgets.items()}
        self.handlers.join(*kwargs.values())

        for entry in self.widgets.entry_widgets.values():
            entry.config(state="readonly")

        # Enable runtime widgets
        self.widgets.group_entry.config(state=tk.NORMAL)
        enable = [self.widgets.update_button, self.widgets.message_input, self.widgets.send_button,
                  self.widgets.online_users_button_refresh, self.widgets.online_users_button_collapse,
                  self.widgets.search_button]
        for w in enable: w.config(state=tk.NORMAL)

        self.widgets.join_button.config(text="Leave", command=self._leave)

    def _leave(self):
        self.state_joined = False
        self.handlers.leave()

        for entry in self.widgets.entry_widgets.values():
            entry.config(state=tk.NORMAL)

        for item in self.widgets.online_users_tree.get_children():
            self.widgets.online_users_tree.delete(item)

        self.widgets.message_text.clear()

        disable = [self.widgets.update_button, self.widgets.message_input, self.widgets.send_button,
                   self.widgets.online_users_button_refresh, self.widgets.online_users_button_collapse,
                   self.widgets.search_button]
        for w in disable: w.config(state=tk.DISABLED)

        self.widgets.join_button.config(text="Join", command=self._join)

    def _update_user(self):
        if not self.state_joined: return
        self.handlers.update_user(self.widgets.group_entry.get())

    def _list_users(self):
        users = self.handlers.list_users()
        for item in self.widgets.online_users_tree.get_children():
            self.widgets.online_users_tree.delete(item)
        for entry in users if users else []:
            user = entry[0]; group = entry[1]
            name = entry[2] if len(entry) > 2 else ""
            last = entry[3] if len(entry) > 3 else ""
            self.widgets.online_users_tree.add_user(user, group, name, last)

    def _send_message(self):
        selected = self.widgets.online_users_tree.selection()
        selected_user = selected[0] if selected else ""
        group = self.widgets.group_entry.get()
        destination = selected_user if selected_user else group
        message = self.widgets.message_input.get()
        self.handlers.send_message(destination, message)
        self.widgets.message_input.delete(0, tk.END)

    def _search_history(self):
        term = self.widgets.search_entry.get().strip()
        self.handlers.search_history(term)


class _GuiWidgets:
    def __init__(self, app: GuiApp):
        self.app = app
        self._create_widgets()
        self._bind_ctrl_backspace()
        self._bind_enter()

    def _create_widgets(self):
        self.root = self.app.root

        # Top inputs
        self.top_frame = ttk.Frame(self.root)
        self.top_frame.pack(fill=tk.X, padx=10, pady=5, anchor=tk.NW)

        self.user_label = ttk.Label(self.top_frame, text="User:")
        self.user_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.user_entry = ttk.Entry(self.top_frame)
        self.user_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)

        self.group_label = ttk.Label(self.top_frame, text="Group:")
        self.group_label.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.group_entry = ttk.Entry(self.top_frame)
        self.group_entry.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W+tk.E)

        self.name_label = ttk.Label(self.top_frame, text="First name:")
        self.name_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.name_entry = ttk.Entry(self.top_frame)
        self.name_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)

        self.last_name_label = ttk.Label(self.top_frame, text="Last name:")
        self.last_name_label.grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.last_name_entry = ttk.Entry(self.top_frame)
        self.last_name_entry.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W+tk.E)

        self.join_button = ttk.Button(self.top_frame, text="Join", command=self.app._join)
        self.join_button.grid(row=0, column=4, padx=5, pady=5)

        self.update_button = ttk.Button(self.top_frame, text="Update", command=self.app._update_user)
        self.update_button.grid(row=1, column=4, padx=5, pady=5)
        self.update_button.config(state=tk.DISABLED)

        self.top_frame.columnconfigure(1, weight=1)
        self.top_frame.columnconfigure(3, weight=1)
        self.entry_widget_names = ["user", "group", "name", "last_name"]
        self.entry_widgets = {
            "user": self.user_entry,
            "group": self.group_entry,
            "name": self.name_entry,
            "last_name": self.last_name_entry
        }

        # Bottom area
        self.bottom_frame = ttk.Frame(self.root)
        self.bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, anchor=tk.NW)
        self.bottom_frame.columnconfigure(0, weight=1)
        self.bottom_frame.rowconfigure(0, weight=1)

        # Message board
        self.message_board_frame = ttk.Frame(self.bottom_frame)
        self.message_board_frame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.NSEW)
        self.message_board_label = ttk.Label(self.message_board_frame, text="Message Board:")
        self.message_board_label.pack(anchor=tk.W)
        self.message_text = tk.Text(self.message_board_frame, height=10, width=50, state=tk.DISABLED)
        def append_line(text_str):
            self.message_text.config(state=tk.NORMAL)
            self.message_text.insert(tk.END, f"{text_str}\n")
            self.message_text.see(tk.END)
            self.message_text.config(state=tk.DISABLED)
        def clear():
            self.message_text.config(state=tk.NORMAL)
            self.message_text.delete("1.0", "end")
            self.message_text.config(state=tk.DISABLED)
        self.message_text.append_line = append_line
        self.message_text.clear = clear
        self.message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.message_scrollbar = ttk.Scrollbar(self.message_board_frame, orient="vertical", command=self.message_text.yview)
        self.message_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_text.config(yscrollcommand=self.message_scrollbar.set)

        # Message input
        self.message_input_frame = ttk.Frame(self.bottom_frame)
        self.message_input_frame.grid(row=1, column=0, padx=5, sticky=tk.NSEW)
        self.message_input = tk.Entry(self.message_input_frame, width=50, font=font.Font(family="Consolas", size=10))
        self.message_input.bind('<Return>', lambda event: self.app._send_message())
        self.message_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.message_input.config(state=tk.DISABLED)
        self.send_button = ttk.Button(self.message_input_frame, text="Send", command=self.app._send_message)
        self.send_button.pack(side=tk.RIGHT)
        self.send_button.config(state=tk.DISABLED)

        # History search
        self.search_frame = ttk.Frame(self.bottom_frame)
        self.search_frame.grid(row=2, column=0, padx=5, pady=(4,0), sticky=tk.W+tk.E)
        self.search_entry = ttk.Entry(self.search_frame)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.insert(0, "Search history...")
        self.search_button = ttk.Button(self.search_frame, text="Search", command=lambda: self.app._search_history())
        self.search_button.pack(side=tk.RIGHT)
        self.search_button.config(state=tk.DISABLED)

        # Online users
        self.online_users_frame = ttk.Frame(self.bottom_frame)
        self.online_users_frame.grid(row=0, column=1, padx=(15,0), pady=5, sticky=tk.NSEW, rowspan=3)

        self.online_users_label_frame = ttk.Frame(self.online_users_frame)
        self.online_users_label_frame.pack(anchor=tk.W, fill=tk.X, pady=(0,5))
        ttk.Label(self.online_users_label_frame, text="Online users:", anchor="w").grid(row=0, column=0, padx=(0, 10), sticky=tk.W)
        self.online_users_button_refresh = ttk.Button(self.online_users_label_frame, text="\u21BB", width=4, command=self.app._list_users)
        self.online_users_button_refresh.grid(row=0, column=1, sticky=tk.E)
        self.online_users_button_refresh.config(state=tk.DISABLED)
        def collapse_cmd():
            self.online_users_button_collapse.state = not self.online_users_button_collapse.state
            for iid in self.online_users_tree.get_children():
                self.online_users_tree.item(iid, open=self.online_users_button_collapse.state)
        self.online_users_button_collapse = ttk.Button(self.online_users_label_frame, text="\u00B1", width=2, command=collapse_cmd)
        self.online_users_button_collapse.state = True
        self.online_users_button_collapse.grid(row=0, column=2, sticky=tk.E)
        self.online_users_button_collapse.config(state=tk.DISABLED)
        self.online_users_label_frame.columnconfigure(0, weight=1)

        self.online_users_list_frame = ttk.Frame(self.online_users_frame)
        self.online_users_list_frame.pack(fill=tk.BOTH, expand=True)
        self.online_users_tree = ttk.Treeview(self.online_users_list_frame, columns=(), show='tree', selectmode='browse')
        def add_user(user, group, name, last_name):
            users = list(self.online_users_tree.get_children())
            for existing_user in users:
                if existing_user == user:
                    existing_group = self.online_users_tree.item(existing_user, "text").split(" (")[-1].rstrip(")")
                    if existing_group == group:
                        logging.exception(f"user {user} already exists in the list with the same group!")
                        return False
                    else:
                        self.online_users_tree.item(existing_user, text=f"{user} ({group})")
                        return True
            users.append(user)
            users.sort()
            self.online_users_tree.insert('', users.index(user), user, text=f"{user} ({group})")
            fullname = f"{name}{(' ' if name and last_name else '')}{last_name}" if (name or last_name) else ""
            if fullname:
                self.online_users_tree.insert(user, 'end', text=fullname)
            self.online_users_tree.item(user, open=self.online_users_button_collapse.state)
            return True
        def delete_user(user):
            if user not in self.online_users_tree.get_children():
                logging.exception(f"user {user} doesn't exist in the list!")
                return False
            self.online_users_tree.delete(user)
            return True
        self.online_users_tree.add_user = add_user
        self.online_users_tree.delete_user = delete_user
        self.online_users_tree.heading('#0', text='User')
        self.online_users_tree.column('#0', width=200)
        self.online_users_tree.selection_prev = None
        def on_select(event):
            selected_item = self.online_users_tree.selection()
            if selected_item:
                if selected_item[0] == self.online_users_tree.selection_prev:
                    self.online_users_tree.selection_remove(selected_item[0])
                    self.online_users_tree.selection_prev = None
                else:
                    parent = self.online_users_tree.parent(selected_item[0])
                    if parent:
                        to_select = self.online_users_tree.selection_prev
                        to_select = "" if to_select is None else to_select
                        self.online_users_tree.selection_prev = None
                        self.online_users_tree.selection_set(to_select)
                    else:
                        self.online_users_tree.selection_prev = selected_item[0]
            else:
                self.online_users_tree.selection_prev = None
        self.online_users_tree.bind('<<TreeviewSelect>>', on_select)
        self.online_users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.online_users_scrollbar = ttk.Scrollbar(self.online_users_list_frame, orient="vertical", command=self.online_users_tree.yview)
        self.online_users_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.online_users_tree.config(yscrollcommand=self.online_users_scrollbar.set)

    def _bind_ctrl_backspace(self):
        def delete_word(event):
            widget = event.widget
            index = widget.index(tk.INSERT)
            text = widget.get()
            while index > 0 and text[index-1] == ' ': index -= 1
            while index > 0 and text[index-1] != ' ': index -= 1
            widget.delete(index, tk.INSERT)
            return 'break'
        for entry in self.entry_widgets.values():
            entry.bind('<Control-BackSpace>', delete_word)
        self.message_input.bind('<Control-BackSpace>', delete_word)
        self.search_entry.bind('<Control-BackSpace>', delete_word)

    def _bind_enter(self):
        for entry in self.entry_widgets.values():
            entry.bind('<Return>', lambda event: self.join_button.invoke())


