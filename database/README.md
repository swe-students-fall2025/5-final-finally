# Database Subsystem (MongoDB)

This subsystem provides the MongoDB database for the AI Diary project.

## Features

- Based on the official `mongo:7` image  
- Automatically initializes the database `ai_diary`
- Creates the main collection: `conversations`
- Creates the required indexes:
  - `{ user_id: 1, date: 1 }`
  - `{ status: 1 }`

## Files

- **Dockerfile** — defines the custom MongoDB container
- **init.js** — initialization script executed on first startup

## Deployment

This subsystem will have its own Dockerfile and CI/CD pipeline, satisfying the project requirement that every subsystem be containerized and individually deployed.
