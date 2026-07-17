# use an official python runtime
FROM python:3.11-slim

# install ffmpeg directly in the container
RUN apt-get update && apt-get install -y ffmpeg

# set the working directory
WORKDIR /app

# copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy everything else
COPY . .

# command to run your bot
CMD ["python", "bot.py"]
