// static/main.js
import { createAppKit } from '@reown/appkit'
import { Ethers5Adapter } from '@reown/appkit-adapter-ethers5'
import { polygon } from '@reown/appkit/networks'  // Assumendo che Reown supporti Polygon, altrimenti definisci manualmente

// 1. Usa il projectId ottenuto da https://cloud.reown.com
const projectId = 'c17f0d55c1fb5debe77f860c40b7afdb'  // il tuo projectId

// 2. Crea l'oggetto metadata per la tua applicazione
const metadata = {
  name: 'GiankyBot',
  description: 'Collega il tuo wallet per usare GiankyCoin sulla rete Polygon',
  url: 'https://gianky-bot-test-f275065c7d33.herokuapp.com', // Deve corrispondere al dominio
  icons: ['https://assets.reown.com/reown-profile-pic.png']
}

// 3. Crea un'istanza di AppKit utilizzando l'adapter per ethers v5
const modal = createAppKit({
  adapters: [new Ethers5Adapter({ projectId, networks: [polygon] })],
  metadata,
  networks: [polygon],
  projectId,
  features: {
    analytics: true
  }
})

// 4. Esporta il modal o collega gli eventi dei pulsanti
// Ad esempio, se nella tua pagina hai un pulsante con id "connectWalletBtn":
document.getElementById('connectWalletBtn')?.addEventListener('click', () => {
  modal.open()  // Apre il modal per il collegamento del wallet
})

// Puoi anche gestire altri eventi (per cambio rete, ecc.) se necessario.
