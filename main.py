import gui
import dds_app
from chat import ChatUser

# Bridges GUI and DDS app
class MainApp:

    def __init__(self):
        # Connect GUI event handlers
        self.gui_handlers = gui.Handlers()
        self.gui_handlers.join           = self.join
        self.gui_handlers.update_user    = self.update_user
        self.gui_handlers.leave          = self.leave
        self.gui_handlers.list_users     = self.list_users
        self.gui_handlers.send_message   = self.send
        self.gui_handlers.search_history = self.search_history

        # Create GUI app instance and pass handlers
        self.gui = gui.GuiApp(self.gui_handlers)

        # Prepare DDS side
        self.dds_user = None
        self.dds_handlers = dds_app.Handlers()
        self.dds_handlers.users_joined    = self.joined
        self.dds_handlers.users_dropped   = self.left
        self.dds_handlers.message_received= self.received
        self.dds_app = None

        self.gui.start() # Start GUI loop
        self.leave() # Clean DDS participant after GUI closes

    # ===== GUI to DDS =====
    # Called when user presses Join
    def join(self, user, group, name, last_name):
        self.dds_user = ChatUser(username=user, group=group,
                                 firstName=(name or ""), lastName=(last_name or ""))
        self.dds_app = dds_app.DDSApp(self.dds_user, self.dds_handlers)

    # Called when user clicks 'Update'
    def update_user(self, group):
        if not self.dds_app: return
        self.dds_app.user_update_group(group=group)

    # when user leaves or exits GUI
    def leave(self):
        if not self.dds_app: return
        self.dds_app.user_leave()

    # Ask DDS to provide current online user list
    def list_users(self):
        if not self.dds_app: return
        user_samples = self.dds_app.user_list()
        return [[s.username, s.group, getattr(s, "firstName", ""), getattr(s, "lastName", "")] for s in user_samples]
    
    # Send message via DDS
    def send(self, destination, message):
        if not self.dds_app: return
        self.dds_app.message_send(destination=destination, message=message)

    # Search message history via DDS
    def search_history(self, keyword: str):
        if not self.dds_app: return
        if not keyword:
            items = self.dds_app.message_history_all(limit=50)
        else:
            items = self.dds_app.message_history_search(keyword, limit=200)
        self.gui.history_results(items)

    # ===== DDS to GUI =====
    # Called when users join
    def joined(self, user_samples):
        users = [[s.username, s.group, getattr(s, "firstName", ""), getattr(s, "lastName", "")] for s in user_samples]
        for user in users: self.gui.user_joined(*user)

    # Called when users leave
    def left(self, user_samples):
        for user in user_samples:
            if self.dds_user and user.username == self.dds_user.username:
                continue
            self.gui.user_left(user.username)

    # Called when messages are received
    def received(self, message_samples):
        messages = [[
            s.fromUser,
            (s.toUser if s.toUser else s.toGroup),
            s.message,
            getattr(s, "timestamp_ms", None)
        ] for s in message_samples]
        for msg in messages:
            self.gui.message_received(*msg)
            
def main():
    return MainApp()

if __name__ == "__main__":
    main()
