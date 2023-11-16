import re
import uuid
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    product_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    description = Column(String(255))
    price = Column(Integer)
    availability_status = Column(String(255))


class Cart(Base):
    __tablename__ = "carts"
    cart_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(255), primary_key=True, index=True)
    product_name = Column(String(255))
    quantity = Column(Integer)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    product = relationship('Product')


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(255), primary_key=True, unique=True, index=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    quantity = Column(Integer)
    product = relationship('Product')


DATABASE_URL = "mysql+mysqlconnector://root:root@localhost/sales_chatbot"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#function to extract session id from dialogflow string
def extract_session_id(session_str: str):
    match = re.search(r"/sessions/(.*?)/contexts/", session_str)
    if match:
        extracted_string = match.group(1)
        return extracted_string
    return ""


@app.post("/")
async def handle_request(request: Request, db: Session = Depends(get_db)):
    # Retrieve JSON data coming from dialogflow
    data = await request.json()

    #Extracting necessary info from dialogflow json

    #different intents are created for dealing with different needs like greeting user,adding products into cart etc
    intent = data['queryResult']['intent']['displayName']

    #product name and quantity of each product are stored in dialogflow entities: product and number
    #these entites are present as arrays inside 'parameters' object inside 'queryResult' object
    parameters = data['queryResult']['parameters']

    #extracting session id
    output_contexts = data['queryResult']['outputContexts']
    session_id = extract_session_id(output_contexts[0]["name"])

    #add.product intent is used for adding products into cart
    if intent == "add.product":
        product_name = parameters["product"][0]
        quantity = parameters["number"][0]

        product = db.query(Product).filter_by(name=product_name).first()

        if product:

            if product.availability_status == "in stock":

                cart_item = Cart(session_id=session_id, product_name=product_name, quantity=quantity,
                                 product_id=product.product_id)
                db.add(cart_item)
                db.commit()

                response_text = f"Added {quantity} {product_name} into your cart. Do you prefer to check your cart, add more items or complete the purchase?"

            else:
                response_text = f"Sorry, {product_name} is currently out of stock."
        else:
            response_text = f"Sorry, we don't have {product_name} at the moment."

    #show.cart intent is used to display cart
    elif intent == "show.cart":

        cart_contents = db.query(Cart).filter_by(session_id=session_id).all()
        cart_items_info = [f"{item.quantity} {item.product_name}" for item in cart_contents]
        response_text = f"Your cart contains: {', '.join(cart_items_info)}. Do you prefer to add more items or complete the purchase?"

    #'purchase.complete' intent is used for completing purchase
    elif intent == 'purchase.complete':

        #store cart items into orders table
        cart_contents = db.query(Cart).filter_by(session_id=session_id).all()

        for cart_item in cart_contents:
            order_item = Order(
                order_id=str(uuid.uuid4()),
                product_id=cart_item.product_id,
                quantity=cart_item.quantity
            )
            db.add(order_item)

        # Removes the items in cart after purchase is complete
        db.query(Cart).filter_by(session_id=session_id).delete()
        db.commit()

        response_text = "Purchase Success. Visit Again"

    #'product.information': when user asks more info about a specific product
    elif intent == 'product.information':
        product_name = parameters["product"]

        # Fetch details of specified product from database and display to user
        if product_name:
            product = db.query(Product).filter_by(name=product_name).first()

            if product:
                response_text = (
                    f"Here it is!!! "
                    f" {product.description}. Rs {product.price}. The {product.name} is {product.availability_status} "

                )
            else:
                response_text = f"Unfortunately, '{product_name}' is unavailable at the moment. ."
        else:
            response_text = f"Sorry,I didn't catch that"

    #product.inquiry intent: when user asks something like "What products do you have"
    elif intent == "product.inquiry":

        products = db.query(Product).all()
        product_titles = [product.name for product in products]

        response_text = f"Here are the available products: {', '.join(product_titles)}"

    #"product.recommend" intent: recommend items to user in random order
    elif intent == "product.recommend":

        random_product = db.query(Product).order_by(func.rand()).first()

        if random_product:
            response_text = (
                f" I recommend {random_product.name}. {random_product.description}."
                f" Price: {random_product.price}."
                f" Availability Status: {random_product.availability_status}"

            )
        else:
            response_text = "Sorry, there are no products available for recommendation at the moment."

    return JSONResponse(content={"fulfillmentText": response_text})
