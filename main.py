import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters
)
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")

# --- Database Setup ---
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    username = Column(String)
    points_balance = Column(Float, default=100.0)

class Recognition(Base):
    __tablename__ = 'recognitions'
    id = Column(Integer, primary_key=True)
    giver_id = Column(String)
    receiver_id = Column(String)
    points = Column(Float)
    message = Column(String)

engine = create_engine('sqlite:///bonusly.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


# --- Helper Functions ---
def get_or_create_user(telegram_id, username):
    session = Session()
    user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
    if not user:
        user = User(telegram_id=str(telegram_id), username=username)
        session.add(user)
        session.commit()
    session.close()
    return user


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /adduser <telegram_id> <username>")
        return
    get_or_create_user(args[0],args[1])



def is_admin(user_id: str) -> bool:
    return str(user_id) in ADMIN_IDS

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    help_text = (
        f"🌟 Welcome {user.username}! Balance: {user.points_balance} points\n\n"
        "Commands:\n"
        "/bonus @user <amount> <message> - Recognize someone\n"
        "/balance - Check points\n"
        "/leaderboard - Top contributors"
    )
    
    if is_admin(str(update.effective_user.id)):
        help_text += "\n\nAdmin Commands:\n/addpoints @user <amount>\n/reset @user\n/announce <msg>\n/userinfo @user\n/export\n/adduser <telegram_id> @username"
    
    await update.message.reply_text(help_text)

async def give_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Format: /bonus @user <amount> <message>")
        return

    receiver_username = args[0].lstrip("@")
    amount = float(args[1])
    message = " ".join(args[2:])

    session = Session()
    try:
        giver = get_or_create_user(update.effective_user.id, update.effective_user.username)
        receiver = session.query(User).filter_by(username=receiver_username).first()

        if not receiver:
            await update.message.reply_text("❌ User not found")
            return
        if giver.points_balance < amount:
            await update.message.reply_text("❌ Insufficient points")
            return

        giver.points_balance -= amount
        receiver.points_balance += amount
        session.add(Recognition(
            giver_id=str(giver.telegram_id),
            receiver_id=str(receiver.telegram_id),
            points=amount,
            message=message
        ))
        session.commit()
        await update.message.reply_text(f"🎉 Gave {amount} points to @{receiver_username}!\nMessage: {message}")
    finally:
        session.close()

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(f"💰 Your balance: {user.points_balance} points")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        top_users = session.query(User).order_by(User.points_balance.desc()).limit(10).all()
        response = "🏆 Leaderboard:\n"
        for idx, user in enumerate(top_users, 1):
            response += f"{idx}. @{user.username}: {user.points_balance}\n"
        await update.message.reply_text(response)
    finally:
        session.close()

# --- Admin Commands ---
async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /addpoints @user <amount>")
        return

    username = args[0].lstrip("@")
    amount = float(args[1])
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ User not found")
            return
        user.points_balance += amount
        session.commit()
        await update.message.reply_text(f"✅ Added {amount} points to @{username}")
    finally:
        session.close()

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /reset @user")
        return

    username = args[0].lstrip("@")
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ User not found")
            return
        user.points_balance = 0
        session.commit()
        await update.message.reply_text(f"✅ Reset @{username}'s points to 0")
    finally:
        session.close()

async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("❌ Usage: /announce <message>")
        return

    session = Session()
    try:
        users = session.query(User).all()
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 Admin Announcement: {message}"
                )
            except Exception as e:
                print(f"Failed to message {user.username}: {e}")
        await update.message.reply_text("✅ Announcement sent to all users")
    finally:
        session.close()

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /userinfo @user")
        return

    username = args[0].lstrip("@")
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ User not found")
            return
        await update.message.reply_text(
            f"👤 @{user.username}\n🆔 {user.telegram_id}\n💰 {user.points_balance} points"
        )
    finally:
        session.close()

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    session = Session()
    try:
        recognitions = session.query(Recognition).all()
        csv_data = "Giver,Receiver,Points,Message\n"
        for rec in recognitions:
            csv_data += f"{rec.giver_id},{rec.receiver_id},{rec.points},{rec.message}\n"
        
        with open("recognitions.csv", "w") as f:
            f.write(csv_data)
        
        await update.message.reply_document(
            document="recognitions.csv",
            caption="📊 Recognition Data Export"
        )
    finally:
        session.close()

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bonus", give_bonus))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    # Admin commands
    app.add_handler(CommandHandler("addpoints", add_points))
    app.add_handler(CommandHandler("reset", reset_user))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("userinfo", user_info))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(CommandHandler("adduser",add_user))
    print("Bot is running...")
    app.run_polling()