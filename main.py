import os
import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
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

engine = create_engine('sqlite:///bonusly.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# --- Scheduler Setup ---
scheduler = AsyncIOScheduler()

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

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        chat_id = str(update.effective_chat.id)
        is_group = update.effective_chat.type in ['group', 'supergroup']
        
        if is_group:
            recognitions = session.query(Recognition).filter_by(group_id=chat_id).all()
            points = {}
            for rec in recognitions:
                points[rec.receiver_id] = points.get(rec.receiver_id, 0.0) + rec.points
            sorted_users = sorted(points.items(), key=lambda x: x[1], reverse=True)[:10]
            response = "🏆 Group Leaderboard:\n"
            for idx, (user_id, total) in enumerate(sorted_users, 1):
                user = session.query(User).filter_by(telegram_id=user_id).first()
                response += f"{idx}. @{user.username if user else 'Unknown'}: {total} points\n"
        else:
            top_users = session.query(User).order_by(User.points_balance.desc()).limit(10).all()
            response = "🏆 Global Leaderboard:\n"
            for idx, user in enumerate(top_users, 1):
                response += f"{idx}. @{user.username}: {user.points_balance} points\n"
        
        await update.message.reply_text(response)
    finally:
        session.close()

# --- Redemption System ---
async def list_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        rewards = session.query(Reward).all()
        response = "🎁 Available Rewards:\n" if rewards else "No rewards available"
        for reward in rewards:
            response += f"\n🆔 {reward.id} {reward.name} ({reward.points_required} points)\n📝 {reward.description}\n"
        await update.message.reply_text(response)
    finally:
        session.close()

async def redeem_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /redeem <reward_id>")
        return
    
    session = Session()
    try:
        reward = session.query(Reward).get(args[0])
        if not reward:
            await update.message.reply_text("❌ Reward not found")
            return
            
        if user.points_balance < reward.points_required:
            await update.message.reply_text("❌ Insufficient points")
            return
            
        request = RedemptionRequest(
            user_id=str(user.telegram_id),
            reward_id=reward.id
        )
        session.add(request)
        
        if not reward.requires_approval:
            user.points_balance -= reward.points_required
            request.status = 'approved'
            session.commit()
            await update.message.reply_text(f"✅ Redeemed {reward.name}!")
        else:
            session.commit()
            await update.message.reply_text("⏳ Reward request sent for approval")
            for admin_id in ADMIN_IDS:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"🆕 Redemption request #{request.id} from @{user.username}"
                )
    finally:
        session.close()

async def approve_redemption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Admin only")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /approve <request_id>")
        return
    
    session = Session()
    try:
        request = session.query(RedemptionRequest).get(args[0])
        if not request or request.status != 'pending':
            await update.message.reply_text("❌ Invalid request")
            return
            
        user = session.query(User).filter_by(telegram_id=request.user_id).first()
        reward = session.query(Reward).get(request.reward_id)
        
        if user.points_balance < reward.points_required:
            await update.message.reply_text("❌ User has insufficient points")
            return
            
        user.points_balance -= reward.points_required
        request.status = 'approved'
        session.commit()
        
        await update.message.reply_text(f"✅ Approved request #{request.id}")
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"🎉 Your {reward.name} redemption was approved!"
        )
    finally:
        session.close()

# --- Recurring Bonuses ---
async def set_recurring_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Usage: /recurring @user <amount> <daily|weekly|monthly>")
        return
    
    receiver_username = args[0].lstrip("@")
    amount = float(args[1])
    interval = args[2].lower()
    
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
            
        next_run = datetime.datetime.now()
        if interval == 'daily':
            next_run += datetime.timedelta(days=1)
        elif interval == 'weekly':
            next_run += datetime.timedelta(weeks=1)
        elif interval == 'monthly':
            next_run = next_run.replace(month=next_run.month + 1)
        else:
            await update.message.reply_text("❌ Invalid interval")
            return
            
        recurring_bonus = RecurringBonus(
            giver_id=str(giver.telegram_id),
            receiver_id=str(receiver.telegram_id),
            amount=amount,
            interval=interval,
            next_run=next_run
        )
        session.add(recurring_bonus)
        session.commit()
        
        await update.message.reply_text(
            f"✅ Set {interval} recurring bonus of {amount} points for @{receiver_username}"
        )
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
    app.add_handler(CommandHandler("approve", approve_redemption))
    app.add_handler(CommandHandler("addpoints", add_points))
    app.add_handler(CommandHandler("reset", reset_user))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("userinfo", user_info))
    app.add_handler(CommandHandler("export", export_data))
    
    # Start scheduler
    scheduler.add_job(process_recurring_bonuses, 'interval', minutes=60)
    scheduler.start()
    
    print("Bot is running...")
    app.run_polling()