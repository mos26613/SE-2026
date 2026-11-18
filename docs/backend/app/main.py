from fastapi import FastAPI 

app = FastAPI(title="Smart Student Task Hub API") 

@app.get("/") 
def read_root():
      return {"message": "Welcome to Smart Student Task Hub API", "status": "online"}