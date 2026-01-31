# Entry point for FastAPI
from fastapi import FastAPI

app = FastAPI(title='Code Intelligence Platform')

@app.get('/')
def health():
    return {'status': 'ok'}
