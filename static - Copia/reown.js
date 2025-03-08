// Esempio di adapt per JavaScript "puro"

// Import from a valid CDN or local if you have a bundler
// QUI serve un Ethers v5 e la libreria @reown/appkit, 
// ma Reown ufficialmente fornisce docs con bundler. 
// Se esiste un CDN di Reown si potrebbe fare un import type=module

// Per semplificare, assumiamo di avere 3 variabili globali (non realistiche!):
//   createAppKit, Ethers5Adapter, mainnet, polygon (al posto di mainnet, arbitrum, ecc.)

// 1. ProjectId da cloud.reown.com
const projectId = "c17f0d55c1fb5debe77f860c40b7afdb";

// 2. Metadata
const metadata = {
  name: "GiankyBot",
  description: "AppKit Example",
  url: "https://gianky-bot-test.herokuapp.com", 
  icons: ["https://assets.reown.com/reown-profile-pic.png"]
};

// 3. Creiamo l'istanza con Ethers5Adapter
export let reownModal; // la esporteremo per usarla altrove
export function initReown() {
  reownModal = createAppKit({
    adapters: [new Ethers5Adapter()],
    // Esempio: sostituisci “mainnet, arbitrum” con “polygon”
    networks: [polygon],
    metadata,
    projectId,
    features: {
      analytics: true 
    }
  });
  console.log("Reown AppKit inizializzato!");
}

// Esempio di funzione per aprire la modal
export function openReownModal() {
  if (!reownModal) initReown();
  reownModal.open();
}
