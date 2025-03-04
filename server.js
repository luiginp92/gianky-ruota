require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { ethers } = require('ethers');

const app = express();
const port = process.env.PORT || 3000;

// Middleware
app.use(bodyParser.json());
app.use(express.static('static')); // Serve i file statici dalla cartella "static"

// Variabili ambiente (assicurati di impostarle nel tuo .env)
const DISTRIBUTION_PRIVATE_KEY = process.env.DISTRIBUTION_PRIVATE_KEY;
const PROVIDER_URL = process.env.PROVIDER_URL || "https://polygon-rpc.com/";
const TOKEN_ADDRESS = process.env.TOKEN_ADDRESS || "0x370806781689E670f85311700445449aC7C3Ff7a";

// Imposta il provider e il wallet di distribuzione
const provider = new ethers.providers.JsonRpcProvider(PROVIDER_URL);
const distributionWallet = new ethers.Wallet(DISTRIBUTION_PRIVATE_KEY, provider);

// ABI minimo per il token ERC20
const tokenAbi = [
  "function transfer(address to, uint amount) public returns (bool)",
  "function decimals() public view returns (uint8)"
];

// Mappa dei premi a quantità da trasferire (in token, 18 decimali)
// Includiamo anche "20 GKY" come premio valido.
const prizeAmounts = {
  "10 GKY": ethers.utils.parseUnits("10", 18),
  "20 GKY": ethers.utils.parseUnits("20", 18),
  "50 GKY": ethers.utils.parseUnits("50", 18),
  "100 GKY": ethers.utils.parseUnits("100", 18),
  "250 GKY": ethers.utils.parseUnits("250", 18),
  "500 GKY": ethers.utils.parseUnits("500", 18),
  "1000 GKY": ethers.utils.parseUnits("1000", 18),
  "NFT BASISC": ethers.BigNumber.from("0"),
  "NFT STARTER": ethers.BigNumber.from("0")
};

const tokenContract = new ethers.Contract(TOKEN_ADDRESS, tokenAbi, distributionWallet);

// Funzione per determinare il premio (distribuzione cumulativa)
// La distribuzione restituisce uno dei seguenti premi:
// "10 GKY", "20 GKY", "50 GKY", "100 GKY", "250 GKY", "500 GKY", "1000 GKY", "NFT BASISC", "NFT STARTER", oppure "NO PRIZE".
function getPrize() {
  let r = Math.random() * 100;
  console.log("Random per premio:", r);
  if (r < 10) return "10 GKY";
  else if (r < 15) return "20 GKY";
  else if (r < 25) return "50 GKY";
  else if (r < 35) return "100 GKY";
  else if (r < 45) return "250 GKY";
  else if (r < 50) return "500 GKY";
  else if (r < 55) return "1000 GKY";
  else if (r < 60) return "NFT BASISC";
  else if (r < 65) return "NFT STARTER";
  else return "NO PRIZE";
}

// Endpoint per distribuire il premio (trasferimento token)
app.post('/api/distribute', async (req, res) => {
  const { walletAddress, prize } = req.body;
  if (!walletAddress || !prize) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (prize === "NO PRIZE") {
    return res.json({ message: "Nessun premio da distribuire" });
  }
  const amount = prizeAmounts[prize];
  if (amount === undefined) {
    return res.status(400).json({ message: "Premio non valido" });
  }
  if (amount.eq(0)) {
    return res.json({ message: `Premio ${prize} assegnato. Verifica la tua collezione NFT.` });
  }
  try {
    const tx = await tokenContract.transfer(walletAddress, amount);
    await tx.wait();
    res.json({ message: `Premio ${prize} distribuito con successo! Transazione: ${tx.hash}` });
  } catch (error) {
    console.error("Errore nella distribuzione del premio:", error);
    res.status(500).json({ message: "Distribuzione fallita" });
  }
});

// Endpoint spin: determina il premio e lo restituisce al client
app.post('/api/spin', async (req, res) => {
  const { wallet_address } = req.body;
  if (!wallet_address) {
    return res.status(400).json({ message: "Wallet address mancante" });
  }
  const prize = getPrize();
  console.log("Premio determinato:", prize);
  res.json({ message: "Spin completato!", prize });
});

// Endpoint per acquistare extra spin (simulato in memoria)
let extraSpinsStore = {};

app.post('/api/buyspins', (req, res) => {
  const { walletAddress, numSpins } = req.body;
  if (!walletAddress || !numSpins) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (![1, 3, 10].includes(numSpins)) {
    return res.status(400).json({ message: "Numero di tiri extra non valido. Valori ammessi: 1, 3, 10" });
  }
  
  let cost;
  if (numSpins === 1) cost = "50";
  else if (numSpins === 3) cost = "125";
  else if (numSpins === 10) cost = "300";
  
  const distributionAddress = distributionWallet.address;
  return res.json({ 
    message: `Per acquistare ${numSpins} tiri extra, trasferisci ${cost} GKY al portafoglio: ${distributionAddress}. Dopo il trasferimento, conferma tramite /api/confirmbuy.` 
  });
});

// Endpoint per confermare l'acquisto degli extra spin (simulato)
app.post('/api/confirmbuy', async (req, res) => {
  const { walletAddress, numSpins, txHash } = req.body;
  if (!walletAddress || !numSpins || !txHash) {
    return res.status(400).json({ message: "Dati mancanti" });
  }
  if (![1, 3, 10].includes(numSpins)) {
    return res.status(400).json({ message: "Numero di tiri extra non valido. Valori ammessi: 1, 3, 10" });
  }
  
  try {
    const tx = await provider.getTransaction(txHash);
    if (!tx) {
      return res.status(400).json({ message: "Transazione non trovata" });
    }
    if (!extraSpinsStore[walletAddress]) {
      extraSpinsStore[walletAddress] = 0;
    }
    extraSpinsStore[walletAddress] += numSpins;
    return res.json({ message: `Acquisto confermato! Ora hai ${extraSpinsStore[walletAddress]} tiri extra.` });
  } catch (error) {
    console.error("Errore nella conferma dell'acquisto:", error);
    return res.status(500).json({ message: "Errore durante la conferma dell'acquisto." });
  }
});

app.listen(port, () => {
  console.log(`Server in ascolto sulla porta ${port}`);
});
