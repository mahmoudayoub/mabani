/**
 * CDK Configuration based on best practices
 * Centralized configuration for environment-specific settings
 */

export interface EnvironmentConfig {
  account: string;
  region: string;
  environment: string;
  domain?: string;
  frontendDomain?: string;
  allowedCorsOrigins: string[];
  enableDetailedMonitoring: boolean;
}

export const environments: Record<string, EnvironmentConfig> = {
  dev: {
    account: "239146712026",
    region: "eu-west-1",
    environment: "dev",
    allowedCorsOrigins: [
      "http://localhost:5173",
      "http://localhost:3000",
      "http://localhost:4173",
    ],
    enableDetailedMonitoring: true,
  },
  staging: {
    account: "239146712026",
    region: "eu-west-1",
    environment: "staging",
    allowedCorsOrigins: ["https://staging.your-domain.com"],
    enableDetailedMonitoring: true,
  },
  prod: {
    account: "239146712026",
    region: "eu-west-1",
    environment: "prod",
    domain: "your-domain.com",
    frontendDomain: "app.your-domain.com",
    allowedCorsOrigins: [
      "https://app.your-domain.com",
      "https://your-domain.com",
    ],
    enableDetailedMonitoring: false,
  },
};

export function getConfig(env: string = "dev"): EnvironmentConfig {
  const config = environments[env];
  if (!config) {
    throw new Error(`Unknown environment: ${env}`);
  }
  return config;
}
