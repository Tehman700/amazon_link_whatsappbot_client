export interface Marketplace {
  id: number;
  code: string;
  name: string;
  domain: string;
}

export interface TrackingID {
  id: number;
  marketplace_id: number;
  tag: string;
  marketplace: Marketplace;
}

export interface User {
  id: number;
  name: string;
  whatsapp_number: string;
  email: string | null;
  link_preference: "direct" | "hub";
  store_name: string;
  tracking_ids: TrackingID[];
}

export interface Replacement {
  original: string;
  rewritten: string;
  marketplace_code: string;
}

export interface SkippedLink {
  url: string;
  reason: string;
}

export interface ProcessResponse {
  text: string;
  links_replaced: number;
  replacements: Replacement[];
  skipped: SkippedLink[];
}

export interface PortalAdminAccount {
  id: number;
  username: string;
  whatsapp_number: string;
  created_at: string;
  disabled: boolean;
  avatar: string;
  store_slug: string;
  store_enabled: boolean;
  bank: string;
  account_title: string;
  account_number: string;
  links: number;
  views: number;
  clicks: number;
  name: string;
  link_preference: string;
  store_name: string;
  linked_numbers: string[];
}

export interface PortalAdminData {
  accounts: PortalAdminAccount[];
  not_signed_up: { name: string; whatsapp_number: string }[];
}
