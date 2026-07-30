# Flask CRM Project

## Project structure

- crm_app/ with the main Flask app and configuration
- database/ with the SQLite database and setup script
- models/ with domain model classes
- api/ with API blueprints
- templates/ with HTML templates
- static/ with CSS and JavaScript assets
- tests/ with pytest coverage

## Run the app

1. Install dependencies:
   ```bash
   pip install -r crm_app/requirements.txt
   ```
2. Initialize the database:
   ```bash
   python database/setup_db.py
   ```
3. Start the app:
   ```bash
   python run.py
   ```
4. Open http://127.0.0.1:5000/.

## Login and role-based access testing

1. Navigate to /login.
2. Sign in with the admin account:
   - Username: admin
   - Password: password123
3. Verify that the admin can view all leads from /leads.
4. Log out and sign in as a normal user:
   - Username: maria
   - Password: password123
5. Verify that the normal user can only see leads they created on /leads.

## View reports

1. Start the Flask app.
2. Open http://127.0.0.1:5000/reports.
3. Review the Lead Status pie chart and the Deal Stage bar chart.

## Run tests

```bash
pytest -q
```

## Deploy to Vercel

1. Push this repository to GitHub.
2. Open Vercel and import the repository.
3. Keep the default project settings.
4. Set the environment variable `SECRET_KEY` to a secure value.
5. Deploy.

The project includes `main.py` and `vercel.json` for Vercel support.
