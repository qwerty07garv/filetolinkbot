FROM caption_bot:latest
WORKDIR /app
RUN pip uninstall -y uvloop 2>/dev/null; \
    rm -rf /usr/local/lib/python3.12/site-packages/uvloop* 2>/dev/null; \
    pip install --no-cache-dir flask pymongo dnspython && \
    echo "ALL DEPS INSTALLED"
COPY bot.py web_server.py db_manager.py ./
COPY templates/ ./templates/
RUN mkdir -p uploads
CMD ["python3", "bot.py"]
