
import json
import os
from flask import Flask, request, jsonify
from datetime import datetime
import firebase_admin
import functions_framework
from firebase_admin import credentials, firestore



# Loading the authentication credentials for the firebase Admin SDK from the 'Key.json'file
cred = credentials.Certificate("key.json")
# Initializing the Firebase Admin SDK using the credentials stored in the 'cred' variable
my_app = firebase_admin.initialize_app(cred)

# Creating a db object to interact with the firebase database
db = firestore.client()



@functions_framework.http
def api_server(request):
    if request.method == 'GET' and request.path == '/voters':
        return get_voter()
    elif request.method == 'POST' and request.path == '/voters':
        return create_voter()
    elif request.method == 'PATCH' and request.path == '/voters/deregister':
        return deregister_voter()
    elif request.method == 'PATCH' and request.path == '/voters/update-voter':
        return update_voter()
    elif request.method == 'DELETE' and request.path == '/voters':
        return deregister_voter()
    
    
    if request.method == 'GET' and request.path == '/elections':
        return get_election()
    elif request.method == 'POST' and request.path == '/elections/<string:election_id>/vote':
        return vote()
    elif request.method == 'POST' and request.path == '/elections/<string:election_id>/insertcandidate':
        return populate_candidate()
    elif request.method == 'POST' and request.path == '/elections':
        return create_election()
    elif request.method == 'DELETE' and request.path == '/elections':
        return delete_election()

    return jsonify("Invalid request")


# GETTING A VOTER IN THE DATABASE

def get_voter():
    student_id = request.args.get("student_id")
    # If student id is provided, then check if it is in the database
    if student_id:
        voters_ref = db.collection('voters')
        query = voters_ref.where('student_id', '==', str(student_id)).limit(1).get()
        if not query:
            return jsonify({'error': 'Sorry, student id not found'}), 404
        else:
            return jsonify(query[0].to_dict())
    # if the student_id wasn't provided, then return all voters
    else:
        voters_ref = db.collection('voters')
        query = voters_ref.stream()
        voters = []
        for doc in query:
            voters.append(doc.to_dict())
        return jsonify(voters)


# CREATING A VOTER
   
def create_voter():
    record = json.loads(request.data)
    # endpoint_path = './tmp/voters.txt'
    # Checking if the student id exists
    student_id = None
    email = None
    for key in record.keys():
        if key.lower() == 'student_id':
            student_id = record.get(key)
        if key.lower() == 'email':
            email = record.get(key)
    # The student_id is a requirement to be a registered voter at Ashesi
    if not student_id:
        return jsonify({'error': 'Student id is missing from the request body'}), 400 #Bad Request
    if not email or not email.endswith('@ashesi.edu.gh'):
        return jsonify({'error': 'Invalid Ashesi email'}), 400
    # Reference to a firestore collection
    voters_ref = db.collection('voters')
    # Limiting the number if documents returned by the query. In this case, the limit is set to 1 (returning at most one document)
    
    #existing_voter = voters_ref.where('student_id', '==', student_id).limit(1).get()
    existing_voter = voters_ref.where('student_id', '==', student_id).get()
    if len(existing_voter) > 0:
        return jsonify({'error': 'Student Id Already Exists'}), 400 # return 400 as the Bad request status code for student id already existing.
    voters_ref.add(record)
    return jsonify({'message': 'Successfully created voter', 'voter': record}), 201 # Created

# DE-REGISTERING A VOTER
"""
A student can be de-registered by passing in the student Id and if they have been registered
as a voter, we can de-register them
Also, we can decide to de-register 
""" 
def deregister_voter():
    param = json.loads(request.data)
    # CHECKING IF THE KEY IN THE REQUEST BODY IS EITHER THE STUDENT_ID OR THE YEAR GROUP
    if "year_group" in param.keys():
        key = "year_group"
    elif "student_id" in param.keys():
        key = "student_id"
    else:
        return jsonify({"error": "Invalid parameter!"}), 404
    
    voters_ref = db.collection('voters')
    query = voters_ref.where(key, '==', param[key]).get()
    if not query:
        return jsonify({'error': f'The {key} {param[key]} provided was not found'}), 404
    
    de_registered = []
    for doc in query:
        record = doc.to_dict()
        if len(param[key]) == 8 and param[key].isnumeric():
            de_registered.append({'message': f"Successfully de-registered voter with ID: {param[key]}"}) 
        elif len(param[key]) == 4 and param[key].isnumeric():
            de_registered.append({'message': f"Successfully de-registered all voters in year: {param[key]}"})
        else:
            return jsonify({"error": "Invalid parameter!"}), 404 
        record['can_vote'] = False
        doc.reference.set(record)
        de_registered.append(record)
        
    return jsonify(*de_registered), 200 # Ok status code




# # UPDATING A REGISTERED VOTER'S INFORMATION
def update_voter():
    student_id = request.args.get("student_id")
    voters_ref = db.collection('voters')
    query = voters_ref.where('student_id', '==', student_id).get()
    if not query:
        return jsonify({'error': 'Student Id Not Found'}), 404 # Not Found
    else:
        for doc in query:
            existing_record = doc.to_dict()
            for key, value in request.json.items():
                existing_record[key] = value
            doc.reference.set(existing_record)
            return jsonify({'message': 'Successfully updated voter'}, existing_record),200 #Status code for update


# # CREATING AN ELECTION

def create_election():
    record = json.loads(request.data)
    required_fields = ['title', 'election_id', 'start_date', 'end_date']
    # Declaring variables as global to be accessed at any point
    global election_id, start_date, end_date, start_datecheck, end_datecheck, title
    for field in required_fields:
        if field not in record.keys():
            return jsonify({'error':'Missing required fields'})
    for key in record.keys():
        # Retrieving the Election ID, start date, and end date of the election
        if key.lower() == 'election_id':
            election_id = record.get(key)
        if key.lower() == 'start_date':
            start_datecheck = record.get(key)
        if key.lower() == 'end_date':
            end_datecheck = record.get(key)
        if key.lower() == 'title':
            title = record.get(key)
    # Throwing an error if the election id was not provided
    if not election_id:
        return jsonify({'error': 'Election id is missing from the request body'}), 400 #Bad Request
    # Checking if both the start and end date follows the correct datetime format
    try:
        start_date = datetime.strptime(start_datecheck,'%Y/%m/%d %H:%M:%S')
        end_date = datetime.strptime(end_datecheck,'%Y/%m/%d %H:%M:%S')
    except ValueError:
        return jsonify({'error':datetime.strptime(record.get(key),'%Y/%m/%d %H:%M:%S') }), 400 #Bad request
    # Ensuring that the end date is less than the start date to ensure that the duration of the election is still valid
    if start_date > end_date:
        return jsonify({'error': 'Start date must come before end date...'}), 400

    # Checking if the election_id already exists in the database
    document_ref = db.collection('elections').document(election_id)
    doc = document_ref.get()
    if doc.exists:
        return jsonify({'error': 'Election Id Already Exists'}), 400

    # Checking if the title already exists in the database
    query = db.collection('elections').where('title', '==', title)
    results = query.get()
    if results:
        return jsonify({'error': 'Title is already taken'}), 400

    # Adding candidates key with an empty array if no records exist in the database
    records = []
    records.append(record)
    record['candidates'] = []

    # Adding record to the database
    document_ref.set(record)

    return jsonify({'message': 'Successfully created an election'}, record), 201 # Status code for successful POST request





# Adding Candidates to an existing election

def populate_candidate():
    election_id = request.args.get("election_id")
    record = json.loads(request.data)
    required_fields = ['name', 'position']
    
    # Find the matching election ID in Firebase
    election_ref = db.collection('elections').document(str(election_id))
    election = election_ref.get()
    if not election.exists:
        return jsonify({'error': f'No election found with id {election_id}'}), 404
    
    # Get the existing candidates or create an empty list if it doesn't exist
    candidates = election.to_dict().get('candidates')
    if candidates is None:
        candidates = []

    # Create a dictionary for the new candidate and append it to the 'candidates' list
    new_candidate = {}
    for field in required_fields:
        if field not in record.keys():
            return jsonify({'error': f'Missing {field} field'}), 400
        new_candidate[field] = record.get(field)
    new_candidate['votes'] = 0
    candidates.append(new_candidate)
    
    # Update the candidates list in Firebase
    election_ref.update({'candidates': candidates})
    
    return jsonify([{"message": "Successfully inserted candidate"}, election.to_dict()]), 201 # Status code for created






# # Deleting an election

def delete_election():
    election_id = request.args.get("election_id")
    # If election id wasn't provided, return an error
    if not election_id:
        return jsonify({'error': 'Election ID was not provided'}), 400  # Bad request
    # Check if the value entered as election_id is an integer
    elif type(election_id) != int:
        return jsonify({'error': 'Election ID provided is not numeric'}), 400  # Bad request

    # Check if election exists
    election_ref = db.collection('elections').document(str(election_id))
    election = election_ref.get()
    if not election.exists:
        return jsonify({'error': f'No election found with id {election_id}'}), 404  # Not found

    # Delete the election document from Firestore
    election_ref.delete()

    return jsonify({'message': f'Successfully deleted the election with id: {election_id}'})


# Retrieving an election

def get_election():
    election_id = request.args.get("election_id")
    # if election_id is provided, check if its in the database and return its details in a dictionary format
    if election_id is not None:
        election = db.collection('elections').document(str(election_id)).get()
        if election.exists:
            return jsonify(election.to_dict())
        else:
            return jsonify({'error': 'Sorry, Election ID was not found'}), 404 # Not found
    
    # If no election_id is not provided, then return the entire elections available
    else:
        elections = db.collection('elections').stream()
        result = []
        for election in elections:
            result.append(election.to_dict())
        return jsonify(result)



# # Voting in an Election

def vote():
    election_id = request.args.get("election_id")
    # Obtaining the JSON format of the data entered by the user in postman
    request_body = json.loads(request.data)
    student_id = request_body.get('student_id')
    election_ref = db.collection('elections').document(str(election_id))
    voted_students_ref = db.collection('voted_students')
    voter_id = student_id
    voter_can_vote = False
    
    # Check if the student is allowed to vote
    voter_ref = db.collection('voters').document(voter_id)
    voter_data = voter_ref.get().to_dict()
    if voter_data:
        voter_can_vote = voter_data.get('can_vote')
        if not voter_can_vote:
            return jsonify({'error': 'You are not allowed to vote.'}), 403
    
    # Check if the student has already voted in this election
    voted_data = voted_students_ref.document(voter_id).get().to_dict()
    if voted_data and voted_data.get(str(election_id)):
        return jsonify({'error': 'You have already voted in this election.'}), 403
    
    # Candidates set to an empty list if there is no candidate and existing_record initialized to an empty dictionary
    candidates = []
    existing_record = {}
    
    # Get election data from the firestore database
    election_data = election_ref.get().to_dict()
    if election_data:
        candidates = election_data.get('candidates')
    else:
        return jsonify({'error': f'Election record with id {election_id} not found.'}), 404
    
    # Loop through the candidates key and update the 'vote' key count for the matching candidate name
    for person in candidates:
        if person['name'] == request_body['name'] and person['position'] == request_body['position']:
            person['votes'] += 1
            existing_record = person
            break
    
    # Update the election data in the firestore database
    election_ref.set(election_data)
    
    # Set the 'election id' value to true in the voted_data collection in firestore and 
    # Update the database that houses all voted_students with the new list of voted students
    if not voted_data:
        voted_data = {}
    voted_data[str(election_id)] = True
    # Updating record in the database
    voted_students_ref.document(voter_id).set(voted_data)
    return jsonify({'message':'You have successfully voted'},existing_record), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


    
    
    
    
    
    
    
    
    


