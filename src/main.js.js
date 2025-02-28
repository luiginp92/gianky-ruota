// Importa le librerie necessarie
import { createAppKit } from '@reown/appkit';
import { Ethers5Adapter } from '@reown/appkit-adapter-ethers5';
import { mainnet, arbitrum } from '@reown/appkit/networks';
import Web3Modal from 'web3modal';
import { ethers } from 'ethers';

// Inserisci il tuo projectId ottenuto da Reown Cloud
const projectId = 'c17f0d55c1fb5debe77f860c40b7afdb';

// Definisci i metadati della tua applicazione
const metadata = {
  name: 'GiankyBot',
  description: 'AppKit Example',
  url: 'https://reown.com/appkit', // L'origine deve corrispondere al tuo dominio
  icons: ['https://assets.reown.com/reown-profile-pic.png']
};

// Crea l'istanza di AppKit (puoi usarla per altre funzionalità, se necessario)
const appKit = createAppKit({
  projectId,
  adapters: [new Ethers5Adapter()],
  networks: [mainnet, arbitrum],
  metadata,
  features: {
    analytics: true
  }
});

// Configura Web3Modal per permettere la scelta del wallet
const web3Modal = new Web3Modal({
  network: "mainnet",      // Puoi modificare la rete se necessario
  cacheProvider: true,     // Abilita la cache del provider, se desiderato
  providerOptions: {}      // Qui puoi aggiungere opzioni per altri provider (es. WalletConnect)
});

// Aggiungi l'evento di click sul bottone per connettere il wallet
document.getElementById('connectWallet').addEventListener('click', async () => {
  try {
    const providerInstance = await web3Modal.connect();
    const ethersProvider = new ethers.providers.Web3Provider(providerInstance);
    const signer = ethersProvider.getSigner();
    const address = await signer.getAddress();
    console.log(`Wallet connesso: ${address}`);
    // Puoi aggiornare la UI con l'indirizzo del wallet o altre info
  } catch (error) {
    console.error("Errore durante la connessione al wallet:", error);
    alert("Connessione al wallet fallita. Riprova.");
  }
});
