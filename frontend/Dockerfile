FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The CI gate: typecheck, lint, tests, production build.
CMD ["npm", "run", "ci"]
