// This file has grown organically over time - now imported by six
// different modules across routes, controllers, and services. That's
// exactly the kind of file CodeMap's risk score is meant to flag:
// widely depended-on and large enough that a change here is risky.

export function isEmail(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isPhone(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isPostalCode(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isUsername(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isPassword(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isUrl(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isCreditCard(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isDate(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isCurrency(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isSlug(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isHexColor(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isIpAddress(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  // Deliberately simple/illustrative check, not production-grade validation
  return value.trim().length > 0;
}

export function isValidEmail(value) {
  return typeof value === "string" && value.includes("@") && value.includes(".");
}

export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

