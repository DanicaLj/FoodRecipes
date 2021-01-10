from flask import Flask, jsonify, render_template, redirect, url_for, request, session
import jwt
from pymongo import MongoClient
from bson import ObjectId
import datetime	
import hashlib
import time
from flask_jwt_extended import (
    JWTManager, jwt_required, create_access_token,
    get_jwt_identity, set_access_cookies
)
from pyhunter import PyHunter
import clearbit

app = Flask(__name__)

clearbit.key = 'sk_93239d46f724d51e2352ae816d173ffc'
app.config['SECRET_KEY'] = 'RandomString'
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_COOKIE_SECURE'] = False
jwt = JWTManager(app)
hunter = PyHunter('e632e8db048e71c89b2280ab9c1b67fc330761aa')

client = MongoClient('mongodb+srv://test:test@cluster0.wiry2.mongodb.net/food_recipes?retryWrites=true&w=majority')
db = client.get_database('food_recipes')

users = db['users']
recipe = db['recipe']
ingredient = db['ingredient']
ingredient_recipe = db['ingredient_recipe']

@app.route('/')
@app.route('/index')
def index():

	return redirect(url_for('login'))

@app.route('/register', methods = ['GET', 'POST'])
def register():
	if request.method == 'GET':
		return render_template('register.html')
	else:
		
		hash_object = hashlib.sha256(request.form['password'].encode())
		password_hashed = hash_object.hexdigest()

		email=request.form['email']
		checkEmail = hunter.email_verifier(email)
		if checkEmail['status'] != 'valid':
			return 'Invalid email address!'
		if users.find_one({"email": request.form['email']}) is not None:
			return 'User already exists, please login!'
		response = clearbit.Enrichment.find(email=email, stream=True)
		fullName = ''
		company = ''
		if response['person'] is not None:
			fullName =  response['person']['name']['fullName']
		if response['company'] is not None:
			company = response['company']['name']
		
		users.insert_one({'firstname':request.form['firstname'], 'lastname':request.form['lastname'],'email':request.form['email'], 'password':password_hashed,
		'fullname' : fullName, 'company' : company})
		return redirect(url_for('login'))

@app.route('/login', methods = ['GET', 'POST'])
def login():
	if request.method == 'GET':
		return render_template('login.html')
	else:
		hash_object = hashlib.sha256(request.form['password'].encode())
		password_hashed = hash_object.hexdigest()
		user = users.find_one({'email':request.form['email'], 'password':password_hashed})
		if user is None:
			return 'Wrong login info!'
		session['_id'] = str(user['_id'])
		access_token = create_access_token(identity={"email": request.form['email']})
		resp = jsonify({'login': True})
		set_access_cookies(resp, access_token)
		return resp, 200

@app.route('/recipe-create', methods = ['GET', 'POST'])
@jwt_required
def recipe_create():
	if request.method == 'GET':
		ingredients = ingredient.find()
		return render_template('recipes-create.html', ingredients = ingredients)
	else:
		ingredients_list = []
		for i in request.form.getlist('ingredients'):
			ingredients_list.append(ObjectId(i))
		
		new_recipe = {
			'name': request.form['name'],
			'user_id': ObjectId(session['_id']),
			'rating_sum' : 0,
			'rating_count' : 0,
			'rate' : 0,
			'description' : request.form['description'],
			'ingredients' :  ingredients_list,
		}

		recipe.insert_one(new_recipe)

		return redirect(url_for('all_recipe'))

@app.route('/recipe-all', methods = ['GET', 'POST'])
@jwt_required
def all_recipe():
	recipes = recipe.find()
	ingredientNames = []
	fullRecipe = []
	
	for n in recipes:
		for recipeIngredients in n['ingredients']:
			ingredientData = ingredient.find_one({'_id' : recipeIngredients})
			ingredientNames.append(ingredientData['name'])
		data={
			'name' : n['name'],
			'_id' : n['_id'],
			'description' : n['description'],
			'rate' : n['rate'],
			'ingredient_name' : ingredientNames,
			'ingredient_count' : len(ingredientNames)
		}
		fullRecipe.append(data)	
		ingredientNames = []		
	topIngredients = top_ingredients()
	return render_template('all-recipes.html', fullRecipe = fullRecipe, topIngredients = topIngredients)

@app.route('/recipe/<id>', methods = ['GET', 'POST'])
@jwt_required
def selcted_recipe(id):
	selectedRecipe = recipe.find_one({'_id': ObjectId(id)})
	return render_template('recipe.html', selectedRecipe = selectedRecipe)

@app.route('/rate-recipe', methods=['GET', 'POST'])
@jwt_required
def rate_recipe():
	selectedRecipe = recipe.find_one({'_id': ObjectId(request.form['recipe_id'])})
	if selectedRecipe['user_id'] == ObjectId(session['_id']):
		return 'You cant rate your own recipe'
	rating_sum = selectedRecipe['rating_sum'] + int(request.form['rate'])
	rating_count = selectedRecipe['rating_count'] + 1
	rate = rating_sum / rating_count
	recipe.update_one({'_id': ObjectId(request.form['recipe_id'])}, {'$set': {'rate': round(rate,2), 'rating_sum': rating_sum, 'rating_count' : rating_count}})
	return redirect(url_for('all_recipe'))

@app.route('/my-recipes', methods=['GET', 'POST'])
@jwt_required
def my_recipes():

	ingredientNames = []
	my_recipes = []
	for n in recipe.find({'user_id':ObjectId(session['_id'])}):
		for recipeIngredients in n['ingredients']:
			ingredientData = ingredient.find_one({'_id' : recipeIngredients})
			ingredientNames.append(ingredientData['name'])
		data={
			'name' : n['name'],
			'_id' : n['_id'],
			'description' : n['description'],
			'rate' : n['rate'],
			'ingredient_name' : ingredientNames
		}
		my_recipes.append(data)	
		ingredientNames = []	
	topIngredients = top_ingredients()
	return render_template('all-recipes.html', fullRecipe = my_recipes, topIngredients = topIngredients)

def most_frequent(List): 
    counter = 0
    num = List[0] 
      
    for i in List: 
        curr_frequency = List.count(i) 
        if(curr_frequency> counter): 
            counter = curr_frequency 
            num = i 
  
    return num 

def top_ingredients():
	recipes = recipe.find()
	allIngredients = []
	topIngredients = []
	for i in recipes:
		for k in i['ingredients']:
			allIngredients.append(k)
	while(len(topIngredients) < 3):	
		top = most_frequent(allIngredients)
		topIngredients.append(top)
		for i in allIngredients:
			if i == top:
				allIngredients.remove(top)
	ingredientName = []
	for i in topIngredients:
		ingredientData = ingredient.find_one({'_id' : i})
		ingredientName.append(ingredientData['name'])
	return ingredientName

if __name__ == '__main__':
	app.run()