FROM python:3.12-slim

# Prevent Python from writing .pyc files & keep stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COPILOT_DISPLAY_HOST="0.0.0.0"

WORKDIR /app

# First copy the required files to install via pip
COPY pyproject.toml README.md VERSION ./
COPY copilot_display ./copilot_display

# Install the application and its dependencies
# Using python-slim avoids long C-extension build times often seen in Alpine
RUN pip install --no-cache-dir .

# Create the configuration directory expected by DataStore
RUN mkdir -p /etc/codisplay

# Expose a volume for application configuration and state
VOLUME ["/etc/codisplay"]

# Expose the default application port
EXPOSE 8420

# For BLE interactions (bleak), you might need to run the container in host network mode
# and map the dbus socket:
# docker run --network host -v /var/run/dbus:/var/run/dbus -v ./data:/etc/codisplay ...
CMD ["copilot-display"]
