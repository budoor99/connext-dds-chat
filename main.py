import gui
import dds_app


class MainApp:
    """Bridge between DDSApp and the GUI."""

    def __init__(self):
        self.gui_handlers = gui.Handlers()
        self.gui_handlers.join = self.join
        self.gui_handlers.update_user = self.update_user
        self.gui_handlers.leave = self.leave
        self.gui_handlers.list_users = self.list_users
        self.gui_handlers.send_message = self.send
        self.gui_handlers.load_history = self.load_history
        self.gui_handlers.search = self.search
        self.gui = gui.GuiApp(self.gui_handlers)

        self.dds_user = None
        self.dds_handlers = dds_app.Handlers()
        self.dds_handlers.users_joined = self.joined
        self.dds_handlers.users_dropped = self.left
        self.dds_handlers.message_received = self.received
        self.dds_app = None

        self.gui.start()

        self.leave()


    def join(self, user, group, name, last_name):
        """Create the DDS app with provided user details and announce join."""
        self.dds_user = dds_app.ChatUser(username=user, group=group, firstName=name, lastName=last_name)
        self.dds_app = dds_app.DDSApp(self.dds_user, self.dds_handlers)

    def update_user(self, group):
        """Change the current user's group (updates partitions/filters)."""
        if not self.dds_app:
            return
        self.dds_app.user_update_group(group=group)

    def leave(self):
        """Leave the chat and tear down DDS entities."""
        if not self.dds_app:
            return
        self.dds_app.user_leave()
        self.dds_app = None

    def list_users(self):
        """Fetch current users from DDS and shape for GUI."""
        if not self.dds_app:
            return
        samples = self.dds_app.user_list()
        return [[s.username, s.group, s.firstName, s.lastName] for s in samples]

    def send(self, destination, message):
        """Send a message to a user or to the group."""
        if not self.dds_app:
            return
        self.dds_app.message_send(destination=destination, message=message)

    def load_history(self):
        """Manually trigger loading of any persisted chat messages."""
        if not self.dds_app:
            return
        self.dds_app.load_history()


    def joined(self, user_samples):
        users = [[s.username, s.group, s.firstName, s.lastName] for s in user_samples]
        for user in users:
            self.gui.user_joined(*user)

    def left(self, user_samples):
        for user in user_samples:
            if self.dds_user and user.username == self.dds_user.username:
                continue
            self.gui.user_left(user.username)

    def received(self, message_samples):
        for s in message_samples:
            dest = s.toUser if s.toUser else (s.toGroup or (self.dds_user.group if self.dds_user else ""))
            self.gui.message_received(s.fromUser, dest, s.message)

    
    def search(self, term):
        if not self.dds_app:
            return []
        return self.dds_app.search_history(term)



def main():
    _ = MainApp()
    return _


if __name__ == "__main__":
    app = main()
