FROM node:22-slim

WORKDIR /app

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy dependency files first for layer caching
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application code (overridden by volume mount in dev)
COPY . .

EXPOSE 5173

# Dev server with HMR, listening on all interfaces
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]
