from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
from io import BytesIO
import threading
import queue
import logging
from logging.handlers import QueueHandler
from datetime import datetime
import appdirs
import webview

# Set up logging and threading
log_queue = queue.Queue()
log_lock = threading.Lock()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
queue_handler = QueueHandler(log_queue)
queue_handler.setFormatter(formatter)
logger.addHandler(queue_handler)

def log_writer():
    while True:
        record = log_queue.get()
        if record is None:
            break
        with log_lock:
            with open('log.txt', 'a') as f:
                f.write(formatter.format(record) + '\n')
        log_queue.task_done()

log_thread = threading.Thread(target=log_writer, daemon=True)
log_thread.start()

# Create Flask app
app = Flask(__name__)

# Configure SQLite database in a persistent user directory
data_dir = appdirs.user_data_dir('PersonalFinanceTracker', 'YourCompanyName')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
db_path = os.path.join(data_dir, 'finance.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'check_same_thread': False}
}
db = SQLAlchemy(app)

# Define database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class InvestmentCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    years = db.Column(db.Integer, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    url = db.Column(db.String(200), nullable=True)  # Added column for URLs
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Investment(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'category_id', name='unique_investment'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('investment_category.id'), nullable=False)
    current_value = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('investments', lazy=True))
    category = db.relationship('InvestmentCategory', backref=db.backref('investments', lazy=True))

class Liability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    user = db.relationship('User', backref=db.backref('liabilities', lazy=True))

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    current_value = db.Column(db.Float, default=0.0)
    rental_income = db.Column(db.Float, default=0.0)

# Helper function to run database operations in a thread
def run_in_thread(func, *args, **kwargs):
    result = [None]
    exception = [None]
    
    def wrapper():
        try:
            with app.app_context():
                result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
            logger.error(f"Thread error in {func.__name__}: {str(e)}")
    
    thread = threading.Thread(target=wrapper)
    thread.start()
    thread.join()
    
    if exception[0]:
        raise exception[0]
    return result[0]

# Initialize database with default data
def init_db():
    logger.info("Initializing database")
    try:
        # Drop all tables to ensure a fresh schema
        db.drop_all()
        logger.info("Dropped existing tables to ensure schema consistency")
        
        # Create all tables based on the current model
        db.create_all()
        logger.info("Created database tables")
        
        # Initialize default users
        if User.query.count() == 0:
            users = ['Sameer', 'Meenakshi', 'Sameeksha', 'Sakshi']
            for name in users:
                user = User(name=name)
                db.session.add(user)
            logger.info("Added default users")
        
        # Initialize default investment categories
        if InvestmentCategory.query.count() == 0:
            categories = [
                {'name': 'Mutual Fund', 'years': 10, 'rate': 12.0, 'url': 'https://symphonia.investwell.app/app/#/login'},
                {'name': 'ICICI Direct', 'years': 8, 'rate': 10.0, 'url': 'https://secure.icicidirect.com/customer/login'},
                {'name': 'ICICI Bank', 'years': 5, 'rate': 6.0, 'url': 'https://www.icicibank.com/personal-banking/insta-banking/internet-banking'},
                {'name': 'Yes Bank', 'years': 5, 'rate': 6.5, 'url': 'https://www.yesbank.in/'},
                {'name': 'PF Account', 'years': 15, 'rate': 8.1, 'url': 'https://unifiedportal-mem.epfindia.gov.in/memberinterface/'},
                {'name': 'Post Office', 'years': 7, 'rate': 7.5, 'url': ''},
                {'name': 'NPS', 'years': 20, 'rate': 10.0, 'url': 'https://cra-nsdl.com/CRA/'},
            ]
            for cat in categories:
                category = InvestmentCategory(name=cat['name'], years=cat['years'], rate=cat['rate'], url=cat['url'])
                db.session.add(category)
            logger.info("Added default investment categories")
        
        # Initialize investments for each user and category
        for user in User.query.all():
            for category in InvestmentCategory.query.all():
                if not Investment.query.filter_by(user_id=user.id, category_id=category.id).first():
                    investment = Investment(user_id=user.id, category_id=category.id, current_value=0.0)
                    db.session.add(investment)
            logger.info(f"Initialized investments for user {user.name}")
        
        # Initialize default properties
        if Property.query.count() == 0:
            properties = ['Pune', 'Bangalore', 'Gurgaon', 'Agra', 'Jaipur']
            for name in properties:
                property = Property(name=name, current_value=0.0, rental_income=0.0)
                db.session.add(property)
            logger.info("Added default properties")
        
        db.session.commit()
        logger.info("Database initialization completed")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing database: {str(e)}")
        raise

# Serve frontend
@app.route('/')
def index():
    logger.info("API_REQUEST: GET / - Serving index.html")
    return send_from_directory('static', 'index.html')

# API Endpoints
@app.route('/api/users', methods=['GET'])
def get_users():
    logger.info("API_REQUEST: GET /api/users")
    try:
        def fetch_users():
            users = User.query.all()
            return [{'id': u.id, 'name': u.name} for u in users]
        users = run_in_thread(fetch_users)
        logger.info(f"Retrieved {len(users)} users")
        return jsonify(users)
    except Exception as e:
        logger.error(f"Error in get_users: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/users', methods=['POST'])
def create_user():
    logger.info("API_REQUEST: POST /api/users")
    try:
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'message': 'Missing name'}), 400
        if User.query.filter_by(name=name).first():
            return jsonify({'message': 'User already exists'}), 409
        user = User(name=name)
        db.session.add(user)
        db.session.commit()
        # Create investments for this user in all categories
        categories = InvestmentCategory.query.all()
        for cat in categories:
            investment = Investment(user_id=user.id, category_id=cat.id, current_value=0.0)
            db.session.add(investment)
        db.session.commit()
        logger.info(f"Created new user: {name}")
        return jsonify({'message': 'User created', 'id': user.id}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/users/<int:id>', methods=['DELETE'])
def delete_user(id):
    logger.info(f"API_REQUEST: DELETE /api/users/{id}")
    try:
        user = User.query.get(id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
        # Delete related investments and liabilities
        investments = Investment.query.filter_by(user_id=id).all()
        for inv in investments:
            db.session.delete(inv)
        liabilities = Liability.query.filter_by(user_id=id).all()
        for liab in liabilities:
            db.session.delete(liab)
        db.session.delete(user)
        db.session.commit()
        logger.info(f"Deleted user ID {id}")
        return jsonify({'message': 'User deleted'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/categories', methods=['GET'])
def get_categories():
    logger.info("API_REQUEST: GET /api/categories")
    try:
        def fetch_categories():
            categories = InvestmentCategory.query.all()
            return [{'id': c.id, 'name': c.name, 'years': c.years, 'rate': c.rate, 'url': c.url, 'last_updated': c.last_updated.isoformat() if c.last_updated else None} for c in categories]
        categories = run_in_thread(fetch_categories)
        logger.info(f"Retrieved {len(categories)} categories")
        return jsonify(categories)
    except Exception as e:
        logger.error(f"Error in get_categories: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/categories', methods=['POST'])
def create_category():
    logger.info("API_REQUEST: POST /api/categories")
    try:
        data = request.get_json()
        name = data.get('name')
        years = data.get('years')
        rate = data.get('rate')
        url = data.get('url')  # Optional field
        if not name or years is None or rate is None:
            return jsonify({'message': 'Missing required fields'}), 400
        if InvestmentCategory.query.filter_by(name=name).first():
            return jsonify({'message': 'Category already exists'}), 409
        category = InvestmentCategory(name=name, years=years, rate=rate, url=url)
        db.session.add(category)
        db.session.commit()
        # Create investment entries for all users
        for user in User.query.all():
            if not Investment.query.filter_by(user_id=user.id, category_id=category.id).first():
                investment = Investment(user_id=user.id, category_id=category.id, current_value=0.0)
                db.session.add(investment)
        db.session.commit()
        logger.info(f"Created new category: {name}")
        return jsonify({'message': 'Category created', 'id': category.id}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating category: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/categories/<int:id>', methods=['PUT'])
def update_category(id):
    logger.info(f"API_REQUEST: PUT /api/categories/{id} - Data: {request.get_json()}")
    try:
        data = request.get_json()
        def update(data):
            category = InvestmentCategory.query.get(id)
            if category:
                category.years = data.get('years', category.years)
                category.rate = data.get('rate', category.rate)
                category.last_updated = datetime.utcnow()
                db.session.commit()
                logger.info(f"Updated category ID {id}: years={category.years}, rate={category.rate}")
                return {'message': 'Updated successfully'}
            logger.warning(f"Category ID {id} not found")
            return {'message': 'Category not found'}, 404
        result = run_in_thread(update, data)
        return jsonify(result[0]) if isinstance(result, tuple) else jsonify(result), result[1] if isinstance(result, tuple) else 200
    except Exception as e:
        logger.error(f"Error in update_category: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/categories/<int:id>', methods=['DELETE'])
def delete_category(id):
    logger.info(f"API_REQUEST: DELETE /api/categories/{id}")
    try:
        category = InvestmentCategory.query.get(id)
        if not category:
            return jsonify({'message': 'Category not found'}), 404
        # Delete related investments
        investments = Investment.query.filter_by(category_id=id).all()
        for inv in investments:
            db.session.delete(inv)
        db.session.delete(category)
        db.session.commit()
        logger.info(f"Deleted category ID {id}")
        return jsonify({'message': 'Category deleted'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting category: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/investments', methods=['GET'])
def get_investments():
    user_id = request.args.get('user_id')
    logger.info(f"API_REQUEST: GET /api/investments - user_id: {user_id}")
    try:
        def fetch_investments():
            if user_id:
                investments = Investment.query.filter_by(user_id=user_id).all()
            else:
                investments = Investment.query.all()
            return [{
                'id': i.id,
                'user_id': i.user_id,
                'category_id': i.category_id,
                'current_value': i.current_value,
                'last_updated': i.last_updated.isoformat() if i.last_updated else None,
                'user_name': i.user.name,
                'category_name': i.category.name,
                'category': {'years': i.category.years, 'rate': i.category.rate}
            } for i in investments]
        investments = run_in_thread(fetch_investments)
        logger.info(f"Retrieved {len(investments)} investments")
        return jsonify(investments)
    except Exception as e:
        logger.error(f"Error in get_investments: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/investments/<int:user_id>/<int:category_id>', methods=['GET', 'PUT'])
def investment_detail(user_id, category_id):
    logger.info(f"API_REQUEST: {request.method} /api/investments/{user_id}/{category_id}")
    try:
        data = request.get_json() if request.method == 'PUT' else None
        def handle_investment(data=None):
            investment = Investment.query.filter_by(user_id=user_id, category_id=category_id).first()
            if not investment:
                investment = Investment(user_id=user_id, category_id=category_id, current_value=0.0)
                db.session.add(investment)
                db.session.commit()
                logger.info(f"Created new investment for user_id={user_id}, category_id={category_id}")
            if data is None:
                return {
                    'user_id': investment.user_id,
                    'category_id': investment.category_id,
                    'current_value': investment.current_value,
                    'last_updated': investment.last_updated.isoformat() if investment.last_updated else None
                }
            else:
                investment.current_value = data.get('current_value', investment.current_value)
                investment.last_updated = datetime.utcnow()
                db.session.commit()
                logger.info(f"Updated investment: user_id={user_id}, category_id={category_id}, current_value={investment.current_value}")
                return {'message': 'Updated successfully'}
        result = run_in_thread(handle_investment, data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in investment_detail: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/liabilities', methods=['GET', 'POST'])
def handle_liabilities():
    logger.info(f"API_REQUEST: {request.method} /api/liabilities")
    try:
        data = request.get_json() if request.method == 'POST' else None
        def handle(data=None):
            if data is None:
                user_id = request.args.get('user_id')
                if user_id:
                    liabilities = Liability.query.filter_by(user_id=user_id).all()
                else:
                    liabilities = Liability.query.all()
                logger.info(f"Retrieved {len(liabilities)} liabilities")
                return [{'id': l.id, 'user_id': l.user_id, 'description': l.description, 'amount': l.amount} for l in liabilities]
            else:
                liability = Liability(user_id=data['user_id'], description=data['description'], amount=data['amount'])
                db.session.add(liability)
                db.session.commit()
                logger.info(f"Added liability: user_id={data['user_id']}, description={data['description']}")
                return {'message': 'Added successfully', 'id': liability.id}
        result = run_in_thread(handle, data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in handle_liabilities: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/properties', methods=['GET'])
def get_properties():
    logger.info("API_REQUEST: GET /api/properties")
    try:
        def fetch_properties():
            properties = Property.query.all()
            return [{'id': p.id, 'name': p.name, 'current_value': p.current_value, 'rental_income': p.rental_income} for p in properties]
        properties = run_in_thread(fetch_properties)
        logger.info(f"Retrieved {len(properties)} properties")
        return jsonify(properties)
    except Exception as e:
        logger.error(f"Error in get_properties: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/properties/<int:id>', methods=['PUT'])
def update_property(id):
    logger.info(f"API_REQUEST: PUT /api/properties/{id} - Data: {request.get_json()}")
    try:
        data = request.get_json()
        def update(data):
            property = Property.query.get(id)
            if property:
                property.current_value = data.get('current_value', property.current_value)
                property.rental_income = data.get('rental_income', property.rental_income)
                db.session.commit()
                logger.info(f"Updated property ID {id}: current_value={property.current_value}, rental_income={property.rental_income}")
                return {'message': 'Updated successfully'}
            logger.warning(f"Property ID {id} not found")
            return {'message': 'Property not found'}, 404
        result = run_in_thread(update, data)
        return jsonify(result[0]) if isinstance(result, tuple) else jsonify(result), result[1] if isinstance(result, tuple) else 200
    except Exception as e:
        logger.error(f"Error in update_property: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/summary/<int:user_id>', methods=['GET'])
def get_summary(user_id):
    logger.info(f"API_REQUEST: GET /api/summary/{user_id}")
    try:
        def fetch_summary():
            user = User.query.get(user_id)
            if not user:
                logger.warning(f"User ID {user_id} not found")
                return {'message': 'User not found'}, 404
            total_assets = db.session.query(db.func.sum(Investment.current_value)).filter_by(user_id=user_id).scalar() or 0.0
            property_total = db.session.query(db.func.sum(Property.current_value)).scalar() or 0.0
            total_assets += property_total
            total_liabilities = db.session.query(db.func.sum(Liability.amount)).filter_by(user_id=user_id).scalar() or 0.0
            net_worth = total_assets - total_liabilities
            investments = Investment.query.filter_by(user_id=user_id).all()
            future_assets = sum(inv.current_value * (1 + inv.category.rate / 100) ** inv.category.years for inv in investments) + property_total
            future_net_worth = future_assets - total_liabilities
            category_totals = {}
            for cat in InvestmentCategory.query.all():
                cat_investments = [inv for inv in investments if inv.category_id == cat.id]
                current_total = sum(inv.current_value for inv in cat_investments)
                future_total = sum(inv.current_value * (1 + cat.rate / 100) ** cat.years for inv in cat_investments)
                category_totals[cat.name.lower().replace(' ', '-')] = {
                    'current_total': current_total,
                    'future_total': future_total
                }
            logger.info(f"Generated summary for user_id={user_id}")
            return {
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'net_worth': net_worth,
                'future_net_worth': future_net_worth,
                'category_totals': category_totals
            }
        result = run_in_thread(fetch_summary)
        return jsonify(result[0]) if isinstance(result, tuple) else jsonify(result), result[1] if isinstance(result, tuple) else 200
    except Exception as e:
        logger.error(f"Error in get_summary: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/summary/all', methods=['GET'])
def get_summary_all():
    logger.info("API_REQUEST: GET /api/summary/all")
    try:
        def fetch_summary_all():
            total_assets = db.session.query(db.func.sum(Investment.current_value)).scalar() or 0.0
            property_total = db.session.query(db.func.sum(Property.current_value)).scalar() or 0.0
            total_assets += property_total
            total_liabilities = db.session.query(db.func.sum(Liability.amount)).scalar() or 0.0
            net_worth = total_assets - total_liabilities
            investments = Investment.query.all()
            future_assets = sum(inv.current_value * (1 + inv.category.rate / 100) ** inv.category.years for inv in investments) + property_total
            future_net_worth = future_assets - total_liabilities
            category_totals = {}
            for cat in InvestmentCategory.query.all():
                cat_investments = [inv for inv in investments if inv.category_id == cat.id]
                current_total = sum(inv.current_value for inv in cat_investments)
                future_total = sum(inv.current_value * (1 + cat.rate / 100) ** cat.years for inv in cat_investments)
                category_totals[cat.name.lower().replace(' ', '-')] = {
                    'current_total': current_total,
                    'future_total': future_total
                }
            logger.info("Generated summary for all users")
            return {
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'net_worth': net_worth,
                'future_net_worth': future_net_worth,
                'category_totals': category_totals
            }
        result = run_in_thread(fetch_summary_all)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get_summary_all: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/last_updated', methods=['GET'])
def get_last_updated():
    logger.info("API_REQUEST: GET /api/last_updated")
    try:
        def fetch_last_updated():
            latest_investment = Investment.query.order_by(Investment.last_updated.desc()).first()
            latest_category = InvestmentCategory.query.order_by(InvestmentCategory.last_updated.desc()).first()
            latest_timestamp = None
            if latest_investment and latest_category:
                latest_timestamp = max(latest_investment.last_updated, latest_category.last_updated)
            elif latest_investment:
                latest_timestamp = latest_investment.last_updated
            elif latest_category:
                latest_timestamp = latest_category.last_updated
            else:
                latest_timestamp = datetime.utcnow()
            logger.info(f"Retrieved last updated timestamp: {latest_timestamp}")
            return {'last_updated': latest_timestamp.isoformat()}
        result = run_in_thread(fetch_last_updated)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get_last_updated: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/check_updates', methods=['GET'])
def check_updates():
    logger.info(f"API_REQUEST: GET /api/check_updates - last_known: {request.args.get('last_known')}")
    try:
        def check():
            last_known = request.args.get('last_known')
            if not last_known:
                return {'updated': True}
            try:
                last_known_dt = datetime.fromisoformat(last_known)
            except ValueError:
                logger.warning("Invalid timestamp format received")
                return {'updated': True}
            latest_investment = Investment.query.order_by(Investment.last_updated.desc()).first()
            latest_category = InvestmentCategory.query.order_by(InvestmentCategory.last_updated.desc()).first()
            latest_timestamp = max(
                latest_investment.last_updated if latest_investment else datetime.min,
                latest_category.last_updated if latest_category else datetime.min
            )
            updated = latest_timestamp > last_known_dt
            logger.info(f"Check updates result: updated={updated}, latest_timestamp={latest_timestamp}")
            return {'updated': updated}
        result = run_in_thread(check)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in check_updates: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

@app.route('/api/export_excel', methods=['GET'])
def export_excel():
    logger.info("API_REQUEST ELECTRONIC: GET /api/export_excel")
    try:
        def generate_excel():
            users = User.query.all()
            categories = InvestmentCategory.query.all()
            investments = Investment.query.all()
            liabilities = Liability.query.all()
            properties = Property.query.all()
            
            # Investments Sheet
            investments_data = []
            for cat in categories:
                cat_data = {'Category': cat.name, 'Years': cat.years, 'Rate (%)': cat.rate}
                for user in users:
                    inv = next((i for i in investments if i.user_id == user.id and i.category_id == cat.id), None)
                    current_value = inv.current_value if inv else 0.0
                    future_value = current_value * (1 + cat.rate / 100) ** cat.years
                    cat_data[f"{user.name} Current (₹)"] = current_value
                    cat_data[f"{user.name} Future (₹)"] = future_value
                cat_data['Current Total (₹)'] = sum(inv.current_value for inv in investments if inv.category_id == cat.id)
                cat_data['Future Total (₹)'] = sum(inv.current_value * (1 + cat.rate / 100) ** cat.years for inv in investments if inv.category_id == cat.id)
                investments_data.append(cat_data)
            investments_df = pd.DataFrame(investments_data)
            
            # Properties Sheet
            properties_data = [{'Property': p.name, 'Current Value (₹)': p.current_value, 'Rental Income (₹)': p.rental_income} for p in properties]
            properties_df = pd.DataFrame(properties_data)
            
            # Liabilities Sheet
            liabilities_data = []
            for liab in liabilities:
                user = next((u for u in users if u.id == liab.user_id), None)
                if user:
                    liabilities_data.append({'User': user.name, 'Description': liab.description, 'Amount (₹)': liab.amount})
            liabilities_df = pd.DataFrame(liabilities_data)
            
            # Summary Sheet
            summary_data = []
            for user in users:
                user_investments = [inv for inv in investments if inv.user_id == user.id]
                total_investments = sum(inv.current_value for inv in user_investments)
                total_properties = sum(p.current_value for p in properties)
                total_assets = total_investments + total_properties
                total_liabilities = sum(liab.amount for liab in liabilities if liab.user_id == user.id)
                net_worth = total_assets - total_liabilities
                future_investments = sum(inv.current_value * (1 + inv.category.rate / 100) ** inv.category.years for inv in user_investments)
                future_net_worth = future_investments + total_properties - total_liabilities
                summary_data.append({
                    'User': user.name,
                    'Total Investments (₹)': total_investments,
                    'Total Properties (₹)': total_properties,
                    'Total Assets (₹)': total_assets,
                    'Total Liabilities (₹)': total_liabilities,
                    'Net Worth (₹)': net_worth,
                    'Future Investments (₹)': future_investments,
                    'Future Net Worth (₹)': future_net_worth
                })
            total_investments_all = sum(inv.current_value for inv in investments)
            total_properties_all = sum(p.current_value for p in properties)
            total_assets_all = total_investments_all + total_properties_all
            total_liabilities_all = sum(liab.amount for liab in liabilities)
            net_worth_all = total_assets_all - total_liabilities_all
            future_investments_all = sum(inv.current_value * (1 + inv.category.rate / 100) ** inv.category.years for inv in investments)
            future_net_worth_all = future_investments_all + total_properties_all - total_liabilities_all
            summary_data.append({
                'User': 'Overall',
                'Total Investments (₹)': total_investments_all,
                'Total Properties (₹)': total_properties_all,
                'Total Assets (₹)': total_assets_all,
                'Total Liabilities (₹)': total_liabilities_all,
                'Net Worth (₹)': net_worth_all,
                'Future Investments (₹)': future_investments_all,
                'Future Net Worth (₹)': future_net_worth_all
            })
            summary_df = pd.DataFrame(summary_data)
            
            # Define export directory as the user's Downloads folder
            downloads_dir = os.path.expanduser("~/Downloads")
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            
            # Generate filename with date and time
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            filename = f'Personal_Finance_Tracker_{timestamp}.xlsx'
            file_path = os.path.join(downloads_dir, filename)
            
            # Save to file
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                investments_df.to_excel(writer, sheet_name='Investments', index=False)
                properties_df.to_excel(writer, sheet_name='Properties', index=False)
                liabilities_df.to_excel(writer, sheet_name='Liabilities', index=False)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Also prepare BytesIO for sending
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                investments_df.to_excel(writer, sheet_name='Investments', index=False)
                properties_df.to_excel(writer, sheet_name='Properties', index=False)
                liabilities_df.to_excel(writer, sheet_name='Liabilities', index=False)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            output.seek(0)
            
            logger.info(f"Generated and saved Excel file at: {file_path}")
            return output, filename
        
        output, filename = run_in_thread(generate_excel)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error in export_excel: {str(e)}")
        return jsonify({'message': 'Internal server error'}), 500

# Run the application with PyWebView
if __name__ == '__main__':
    with app.app_context():
        logger.info("Starting application")
        run_in_thread(init_db)
    
    def start_flask():
        app.run(debug=False, threaded=True)
    
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    webview.create_window('Personal Finance Tracker', 'http://127.0.0.1:5000')
    webview.start()
    
    logger.info("Application shutdown")
    log_queue.put(None)