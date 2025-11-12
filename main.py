# main.py
import gui
import dds_app
from chat import ChatUser

class MainApp:
    """Bridges GUI and DDS app."""

    def __init__(self):
        # GUI handlers
        self.gui_handlers = gui.Handlers()
        self.gui_handlers.join           = self.join
        self.gui_handlers.update_user    = self.update_user
        self.gui_handlers.leave          = self.leave
        self.gui_handlers.list_users     = self.list_users
        self.gui_handlers.send_message   = self.send
        self.gui_handlers.search_history = self.search_history

        self.gui = gui.GuiApp(self.gui_handlers)

        # DDS
        self.dds_user = None
        self.dds_handlers = dds_app.Handlers()
        self.dds_handlers.users_joined    = self.joined
        self.dds_handlers.users_dropped   = self.left
        self.dds_handlers.message_received= self.received
        self.dds_app = None

        self.gui.start()
        self.leave()

    # GUI -> DDS
    def join(self, user, group, name, last_name):
        self.dds_user = ChatUser(username=user, group=group,
                                 firstName=(name or ""), lastName=(last_name or ""))
        self.dds_app = dds_app.DDSApp(self.dds_user, self.dds_handlers)

    def update_user(self, group):
        if not self.dds_app: return
        self.dds_app.user_update_group(group=group)

    def leave(self):
        if not self.dds_app: return
        self.dds_app.user_leave()

    def list_users(self):
        if not self.dds_app: return
        user_samples = self.dds_app.user_list()
        return [[s.username, s.group, getattr(s, "firstName", ""), getattr(s, "lastName", "")] for s in user_samples]

    def send(self, destination, message):
        if not self.dds_app: return
        self.dds_app.message_send(destination=destination, message=message)

    def search_history(self, keyword: str):
        if not self.dds_app: return
        if not keyword:
            items = self.dds_app.message_history_all(limit=50)
        else:
            items = self.dds_app.message_history_search(keyword, limit=200)
        self.gui.history_results(items)

    # DDS -> GUI
    def joined(self, user_samples):
        users = [[s.username, s.group, getattr(s, "firstName", ""), getattr(s, "lastName", "")] for s in user_samples]
        for user in users: self.gui.user_joined(*user)

    def left(self, user_samples):
        for user in user_samples:
            if self.dds_user and user.username == self.dds_user.username:
                continue
            self.gui.user_left(user.username)

    def received(self, message_samples):
        messages = [[s.fromUser, s.toUser, s.message] for s in message_samples]
        for msg in messages: self.gui.message_received(*msg)

def main():
    return MainApp()

if __name__ == "__main__":
    main()
