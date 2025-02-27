// main.ts
import { createAppKit } from '@reown/appkit';
import { Ethers5Adapter } from '@reown/appkit-adapter-ethers5';
// Se Reown AppKit supporta già Polygon, prova a importarlo direttamente; 
// altrimenti, potresti dover usare il network mainnet o definire un network personalizzato.
import { polygon } from '@reown/appkit/networks';  

// 1. Ottieni il Project ID da WalletConnect Cloud
const projectId = 'c17f0d55c1fb5debe77f860c40b7afdb';

// 2. Configura i metadata della tua app; assicurati che l'URL corrisponda esattamente al dominio del deploy.
const metadata = {
  name: 'GiankyCoin',
  description: 'Collega il tuo wallet per usare GiankyCoin sulla rete Polygon',
  url: 'https://gianky-bot-test-f275065c7d33.herokuapp.com', // Deve corrispondere al dominio esatto
  icons: ['https://assets.reown.com/reown-profile-pic.png']
};

// 3. Crea l'istanza di AppKit
const modal = createAppKit({
  adapters: [new Ethers5Adapter()],
  metadata: metadata,
  networks: [polygon],
  projectId: projectId,
  features: {
    analytics: true // Opzionale, si sincronizza con le impostazioni nel Cloud
  }
});

// Esporta il modal per poterlo usare in altri moduli o per l'apertura del modal da un pulsante
export default modal;
