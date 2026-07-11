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
