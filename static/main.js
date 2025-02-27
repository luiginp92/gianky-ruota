// Importa le funzioni e gli adapter necessari
import { createAppKit } from '@reown/appkit';
import { Ethers5Adapter } from '@reown/appkit-adapter-ethers5';
import { mainnet, arbitrum } from '@reown/appkit/networks';

// 1. Ottieni il projectId da https://cloud.reown.com
const projectId = 'YOUR_PROJECT_ID'; // Sostituisci con il tuo Project ID

// 2. Crea l'oggetto metadata della tua applicazione
const metadata = {
  name: 'My Website',
  description: 'My Website description',
  url: 'https://mywebsite.com', // Assicurati che l’URL corrisponda al dominio e subdominio della tua app
  icons: ['https://avatars.mywebsite.com/']
};

// 3. Crea l’istanza di AppKit
const appkitModal = createAppKit({
  adapters: [new Ethers5Adapter()],
  metadata: metadata,
  networks: [mainnet, arbitrum],
  projectId,
  features: {
    analytics: true // Opzionale, in base alla configurazione del Cloud
  }
});

// Gestione dell'evento di connessione
appkitModal.on('connect', (data) => {
  console.log('Wallet connesso:', data);
  // Aggiorna l'interfaccia con le informazioni del wallet
  document.getElementById('wallet-address').textContent = `Wallet: ${data.walletAddress}`;
  // Se il backend restituisce anche i saldi, aggiorna anche questi campi (esempio)
  if (data.balances) {
    document.getElementById('giankycoin-balance').textContent = `GiankyCoin: ${data.balances.giankyCoin || 0}`;
    document.getElementById('matic-balance').textContent = `MATIC: ${data.balances.matic || 0}`;
  }
});

// Esempio di gestione degli altri pulsanti (placeholder)
document.getElementById('spin-btn').addEventListener('click', () => {
  alert('Funzionalità Spin non ancora implementata.');
});

document.getElementById('acquista-btn').addEventListener('click', () => {
  alert('Funzionalità Acquista non ancora implementata.');
});

document.getElementById('referral-btn').addEventListener('click', () => {
  alert('Funzionalità Referral non ancora implementata.');
});

document.getElementById('task-btn').addEventListener('click', () => {
  alert('Funzionalità Task non ancora implementata.');
});
