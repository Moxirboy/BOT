# Rahmat Telegram Bot

This is a Telegram bot implementation of the Rahmat system, designed to allow users to give recognition points to each other, manage rewards, and track leaderboards. The bot supports both individual and group interactions, with additional admin features for managing organizations, users, and rewards.

---

## Features

### User Features:
- **Give Points**: Users can give points to others with a message and optional tags.
- **Check Balance**: Users can view their current points balance.
- **Leaderboard**: View the top contributors in a group or globally.
- **Redeem Rewards**: Users can redeem points for rewards (requires admin approval for some rewards).
- **Recurring Bonuses**: Set up automatic recurring bonuses for team members.

### Admin Features:
- **Add/Remove Points**: Admins can add or reset points for users.
- **Announcements**: Send announcements to all users.
- **User Management**: Add users to organizations and manage their details.
- **Organization Management**: Create and manage organizations, link Telegram groups, and import members.
- **Export Data**: Export recognition data as a CSV file.
- **Approve Redemptions**: Approve or reject reward redemption requests.

---

## Setup Instructions

### Prerequisites
1. Python 3.8 or higher.
2. A Telegram bot token from [BotFather](https://core.telegram.org/bots#botfather).
3. A `.env` file with the following variables:
   ```ini
   BOT_TOKEN=your_telegram_bot_token
   ADMIN_IDS=your_admin_user_id
   ORG_ADMIN_PASSWORD=your_secure_password
   ```

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/rahmat-telegram-bot.git
   cd rahmat-telegram-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Initialize the database:
   ```bash
   python main.py
   ```
   This will create a `rahmat.db` SQLite database file.

4. Run the bot:
   ```bash
   python main.py
   ```

---

## Usage

### User Commands
- `/start` - Start the bot and view available commands.
- `/bonus @user <amount> #tag <message>` - Give points to a user.
- `/balance` - Check your points balance.
- `/leaderboard` - View the leaderboard.
- `/rewards` - List available rewards.
- `/redeem <reward_id>` - Redeem points for a reward.
- `/recurring @user <amount> <daily|weekly|monthly>` - Set up a recurring bonus.

### Admin Commands
- `/addpoints @user <amount>` - Add points to a user.
- `/reset @user` - Reset a user's points to 0.
- `/announce <message>` - Send an announcement to all users.
- `/userinfo @user` - View user details.
- `/export` - Export recognition data as a CSV file.
- `/addorg` - Create a new organization.
- `/org_adduser` - Add a user to an organization.
- `/approve <request_id>` - Approve a reward redemption request.

---

## Database Schema

The bot uses SQLite to store data. The database schema includes the following tables:

- **users**: Stores user information (Telegram ID, username, points balance).
- **recognitions**: Tracks points given between users.
- **rewards**: Stores available rewards and their point requirements.
- **redemption_requests**: Tracks reward redemption requests.
- **organizations**: Stores organization details.
- **user_organizations**: Links users to organizations.
- **groups**: Links Telegram groups to organizations.
- **comments**: Stores comments on recognitions.

---

## Troubleshooting

### Common Issues
1. **Bot not responding**:
   - Ensure the bot is running and has the correct `BOT_TOKEN`.
   - Check if another instance of the bot is running (conflict error).

2. **Database errors**:
   - Ensure the `rahmat.db` file exists and is writable.
   - If the schema changes, delete the database file and restart the bot to recreate it.

3. **Admin commands not working**:
   - Verify your Telegram user ID is in the `ADMIN_IDS` list in the `.env` file.

4. **Organization creation issues**:
   - Ensure the bot is an admin in the Telegram group you're linking.
   - Verify the `ORG_ADMIN_PASSWORD` is correctly set in the `.env` file.

---

## Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Submit a pull request with a detailed description of your changes.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram bot framework.
- [SQLAlchemy](https://www.sqlalchemy.org/) for database management.
- [rahmat](https://rahmat.com/) for inspiration.

---

## Contact

For questions or support, please open an issue on GitHub or contact the info@binaryhood.uz .
