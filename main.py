# main.py
import os
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
    tags = Column(String)
    group_id = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)

class Reward(Base):
    __tablename__ = 'rewards'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    points_required = Column(Float)
    requires_approval = Column(Boolean, default=True)

class RedemptionRequest(Base):
    __tablename__ = 'redemption_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(String)
    reward_id = Column(Integer)
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=datetime.datetime.now)

class RecurringBonus(Base):
    __tablename__ = 'recurring_bonuses'
    id = Column(Integer, primary_key=True)
    giver_id = Column(String)
    receiver_id = Column(String)
    amount = Column(Float)
    interval = Column(String)
    next_run = Column(DateTime)
    is_active = Column(Boolean, default=True)

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    admin_id = Column(String)

class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    org_id = Column(Integer)
    group_name = Column(String)
    telegram_group_id = Column(String)
    is_public = Column(Boolean, default=True)

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    recognition_id = Column(Integer)
    user_id = Column(String)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)

engine = create_engine('sqlite:///bonusly.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# --- Scheduler Setup ---
scheduler = AsyncIOScheduler()

# --- Conversation States ---
ORG_CHOOSE, GROUP_CHOOSE, RECEIVER_CHOOSE, AMOUNT_INPUT, MESSAGE_INPUT = range(5)

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

def is_admin(user_id: str) -> bool:
    return str(user_id) in ADMIN_IDS

def get_org_groups(org_id):
    session = Session()
    groups = session.query(Group).filter_by(org_id=org_id).all()
    session.close()
    return groups

def get_user_organizations(user_id):
    session = Session()
    orgs = session.query(Organization).filter_by(admin_id=str(user_id)).all()
    session.close()
    return orgs

async def process_recurring_bonuses():
    session = Session()
    now = datetime.datetime.now()
    try:
        bonuses = session.query(RecurringBonus).filter(
            RecurringBonus.next_run <= now,
            RecurringBonus.is_active == True
        ).all()
        for bonus in bonuses:
            giver = session.query(User).filter_by(telegram_id=bonus.giver_id).first()
            receiver = session.query(User).filter_by(telegram_id=bonus.receiver_id).first()
            if not giver or not receiver:
                continue
            if giver.points_balance < bonus.amount:
                continue
            
            giver.points_balance -= bonus.amount
            receiver.points_balance += bonus.amount
            
            session.add(Recognition(
                giver_id=bonus.giver_id,
                receiver_id=bonus.receiver_id,
                points=bonus.amount,
                message=f"Recurring bonus ({bonus.interval})",
                group_id=None
            ))
            
            if bonus.interval == 'daily':
                bonus.next_run = now + datetime.timedelta(days=1)
            elif bonus.interval == 'weekly':
                bonus.next_run = now + datetime.timedelta(weeks=1)
            elif bonus.interval == 'monthly':
                bonus.next_run = now.replace(month=now.month + 1)
            
            session.commit()
            
            await app.bot.send_message(
                chat_id=giver.telegram_id,
                text=f"♻️ Sent recurring {bonus.amount} points to @{receiver.username}"
            )
            await app.bot.send_message(
                chat_id=receiver.telegram_id,
                text=f"♻️ Received {bonus.amount} points from @{giver.username}"
            )
    finally:
        session.close()

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    help_text = (
        f"🌟 Welcome {user.username}! Balance: {user.points_balance} points\n\n"
        "Commands:\n"
        "/bonus @user <amount> #tag <message> - Give points\n"
        "/recognize - Post recognition to a group\n"
        "/balance - Check balance\n"
        "/leaderboard - Group/Global leaderboard\n"
        "/rewards - Available rewards\n"
        "/redeem <reward_id> - Redeem points\n"
        "/recurring @user <amount> <interval> - Set recurring bonus"
    )
    
    if is_admin(str(update.effective_user.id)):
        help_text += "\n\nAdmin Commands:\n/addpoints\n/reset\n/announce\n/userinfo\n/export\n/approve"
    
    await update.message.reply_text(help_text)

async def give_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("❌ Format: /bonus @user <amount> #tag <message>")
        return

    receiver_username = args[0].lstrip("@")
    amount = float(args[1])
    tags = [arg for arg in args[2:] if arg.startswith("#")]
    message = " ".join([arg for arg in args[2:] if not arg.startswith("#")])
    group_id = str(update.effective_chat.id) if update.effective_chat.type in ['group', 'supergroup'] else None

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
        
        recognition = Recognition(
            giver_id=str(giver.telegram_id),
            receiver_id=str(receiver.telegram_id),
            points=amount,
            message=message,
            tags=",".join(tags),
            group_id=group_id
        )
        session.add(recognition)
        session.commit()
        
        response = f"🎉 Gave {amount} points to @{receiver_username}"
        if tags:
            response += f"\n🏷 Tags: {', '.join(tags)}"
        response += f"\n📝 Message: {message}"
        
        await update.message.reply_text(response)
        await context.bot.send_message(
            chat_id=receiver.telegram_id,
            text=f"🎉 Received {amount} points from @{giver.username}\n📝 {message}"
        )
    finally:
        session.close()

# --- Cross-Group Recognition Flow ---
async def start_cross_group_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_orgs = get_user_organizations(update.effective_user.id)
    if not user_orgs:
        await update.message.reply_text("❌ You don't belong to any organizations")
        return ConversationHandler.END
    
    buttons = [[InlineKeyboardButton(org.name, callback_data=f"org_{org.id}")] for org in user_orgs]
    await update.message.reply_text(
        "🏢 Select your organization:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ORG_CHOOSE

async def org_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    org_id = int(query.data.split("_")[1])
    context.user_data['org_id'] = org_id
    
    groups = get_org_groups(org_id)
    buttons = [[InlineKeyboardButton(group.group_name, callback_data=f"group_{group.id}")] for group in groups]
    await query.edit_message_text(
        "📚 Select a group:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return GROUP_CHOOSE

async def group_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    group_id = int(query.data.split("_")[1])
    context.user_data['group_id'] = group_id
    
    await query.edit_message_text("👤 Please mention or enter the username of the person you want to recognize:")
    return RECEIVER_CHOOSE

async def receiver_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    receiver_username = update.message.text.lstrip("@")
    context.user_data['receiver'] = receiver_username
    
    await update.message.reply_text("💰 Enter the amount of points to give:")
    return AMOUNT_INPUT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        context.user_data['amount'] = amount
        
        await update.message.reply_text("📝 Write your recognition message:")
        return MESSAGE_INPUT
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a number:")
        return AMOUNT_INPUT

async def message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    context.user_data['message'] = message
    
    session = Session()
    try:
        user_data = context.user_data
        giver = get_or_create_user(update.effective_user.id, update.effective_user.username)
        receiver = session.query(User).filter_by(username=user_data['receiver']).first()
        group = session.query(Group).get(user_data['group_id'])

        if not receiver or not group:
            await update.message.reply_text("❌ Error: User or group not found")
            return ConversationHandler.END

        if giver.points_balance < user_data['amount']:
            await update.message.reply_text("❌ Insufficient points")
            return ConversationHandler.END

        giver.points_balance -= user_data['amount']
        receiver.points_balance += user_data['amount']

        recognition = Recognition(
            giver_id=str(giver.telegram_id),
            receiver_id=str(receiver.telegram_id),
            points=user_data['amount'],
            message=message,
            group_id=group.telegram_group_id
        )
        session.add(recognition)
        session.commit()

        keyboard = [
            [
                InlineKeyboardButton("👍", callback_data=f"react_{recognition.id}_like"),
                InlineKeyboardButton("💬 Comment", callback_data=f"comment_{recognition.id}")
            ]
        ]

        msg_text = f"🎉 Recognition in {group.group_name}!\nFrom: @{giver.username}\nTo: @{receiver.username}\nAmount: {user_data['amount']}\nMessage: {message}"
        await context.bot.send_message(
            chat_id=group.telegram_group_id,
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text("✅ Recognition posted successfully!")
        
    finally:
        session.close()
    return ConversationHandler.END

# --- Interactive Features ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    
    if data[0] == "react":
        recognition_id = data[1]
        reaction_type = data[2]
        user = get_or_create_user(query.from_user.id, query.from_user.username)
        
        session = Session()
        try:
            recognition = session.query(Recognition).get(recognition_id)
            if recognition:
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"👍 {reaction_type}", callback_data="dummy"),
                    InlineKeyboardButton("💬 Comment", callback_data=f"comment_{recognition_id}")
                ]]))
        finally:
            session.close()

    elif data[0] == "comment":
        recognition_id = data[1]
        context.user_data['comment_recognition'] = recognition_id
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="💬 Enter your comment:"
        )

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recognition_id = context.user_data.get('comment_recognition')
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    
    session = Session()
    try:
        comment = Comment(
            recognition_id=recognition_id,
            user_id=str(user.telegram_id),
            text=update.message.text
        )
        session.add(comment)
        session.commit()

        recognition = session.query(Recognition).get(recognition_id)
        if recognition and recognition.group_id:
            await context.bot.send_message(
                chat_id=recognition.group_id,
                text=f"💬 @{user.username}: {update.message.text}",
                reply_to_message_id=recognition.id
            )
        
        await update.message.reply_text("💬 Comment posted!")
    finally:
        session.close()

# --- Admin Commands ---
async def add_org(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Usage: /addorg <org_name> <admin_id>")
        return
    
    session = Session()
    try:
        org = Organization(name=args[0], admin_id=args[1])
        session.add(org)
        session.commit()
        await update.message.reply_text(f"✅ Organization {args[0]} created")
    finally:
        session.close()

async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /addgroup <org_id> <group_name> <telegram_group_id>")
        return
    
    session = Session()
    try:
        group = Group(
            org_id=int(args[0]),
            group_name=args[1],
            telegram_group_id=args[2]
        )
        session.add(group)
        session.commit()
        await update.message.reply_text(f"✅ Group {args[1]} added to organization")
    finally:
        session.close()

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bonus", give_bonus))
    app.add_handler(CommandHandler("balance", lambda u,c: u.message.reply_text(f"💰 Balance: {get_or_create_user(u.effective_user.id, u.effective_user.username).points_balance}")))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("rewards", list_rewards))
    app.add_handler(CommandHandler("redeem", redeem_reward))
    app.add_handler(CommandHandler("recurring", set_recurring_bonus))
    
    # Admin commands
    app.add_handler(CommandHandler("addorg", add_org))
    app.add_handler(CommandHandler("addgroup", add_group))
    app.add_handler(CommandHandler("approve", approve_redemption))
    app.add_handler(CommandHandler("addpoints", add_points))
    app.add_handler(CommandHandler("reset", reset_user))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("userinfo", user_info))
    app.add_handler(CommandHandler("export", export_data))
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('recognize', start_cross_group_bonus)],
        states={
            ORG_CHOOSE: [CallbackQueryHandler(org_chosen)],
            GROUP_CHOOSE: [CallbackQueryHandler(group_chosen)],
            RECEIVER_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiver_chosen)],
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            MESSAGE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_received)]
        },
        fallbacks=[]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))
    
    # Start scheduler
    scheduler.add_job(process_recurring_bonuses, 'interval', minutes=60)
    scheduler.start()
    
    print("Bot is running...")
    app.run_polling()