# Dockerfile

# 1) Use the Playwright image matching your installed version
FROM mcr.microsoft.com/playwright:v1.53.1-focal

# 2) Create app directory
WORKDIR /app

# 3) Copy package manifests
COPY package.json package-lock.json ./

# 4) Install dependencies (will run postinstall if you set it up)
RUN npm ci

# 5) Copy the rest of the code
COPY . .

# 6) Expose port (Render will map automatically)
EXPOSE 3000

# 7) Start your server
CMD ["npm", "start"]
