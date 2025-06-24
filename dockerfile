# Dockerfile

# 1) Use the Playwright image which already has browsers & deps
FROM mcr.microsoft.com/playwright:focal

# 2) Set workdir and copy package files
WORKDIR /app
COPY package.json package-lock.json ./

# 3) Install Node modules (runs postinstall to fetch playwright browsers)
RUN npm ci

# 4) Copy the rest of your app
COPY . .

# 5) Expose the port your Express server listens on
EXPOSE 3000

# 6) Launch your server
CMD ["npm", "start"]
