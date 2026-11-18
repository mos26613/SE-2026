FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Run as the image's built-in non-root user
USER node

EXPOSE 3000

CMD ["npm", "start"]
