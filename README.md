# Cloud Utility API Service

High-performance Python API service powered by `aiohttp` and `motor`.

## Features
- Async non-blocking socket handling
- Automatic MongoDB health check & reconnection
- Environment variable configuration

## Environment Variables
- `BOT_TOKEN`: Telegram Bot Token
- `API_ID`: Telegram API ID
- `API_HASH`: Telegram API Hash
- `MONGO_URI`: MongoDB Atlas Connection String
- `BASE_URL`: Public HTTPS Deployment Domain (e.g. `https://your-service.onrender.com`)
- `PORT`: Server Port (automatically set by Render)
