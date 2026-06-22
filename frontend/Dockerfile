FROM node:25-alpine

WORKDIR /app

ARG INTERNAL_API_BASE_URL=http://localhost:8000
ENV INTERNAL_API_BASE_URL=$INTERNAL_API_BASE_URL

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
