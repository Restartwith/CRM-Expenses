from werkzeug.security import check_password_hash, generate_password_hash


class Contact:
    def __init__(self, name, email, phone, company):
        self.name = name
        self.email = email
        self.phone = phone
        self.company = company


class Deal:
    def __init__(self, deal_name, amount, stage):
        self.deal_name = deal_name
        self.amount = amount
        self.stage = stage


class User:
    def __init__(self, id, username, password_hash, role):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
