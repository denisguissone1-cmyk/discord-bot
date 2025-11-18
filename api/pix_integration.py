"""
Integração com APIs de pagamento PIX

APIs Sugeridas:
1. Mercado Pago - Mais conhecida, taxas maiores (~4.99%)
2. OpenPix - Brasileira, taxas menores (~1.99%), específica para PIX
3. PagSeguro - Alternativa tradicional
4. Asaas - Excelente para automação, taxas competitivas (~1.99%)
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import PaymentConfig
import hashlib
import hmac

# =============================================
# MERCADO PAGO
# =============================================

class MercadoPagoAPI:
    """
    Mercado Pago - API oficial
    Documentação: https://www.mercadopago.com.br/developers/pt/docs/checkout-api/landing
    
    Vantagens:
    - Mais conhecida e confiável
    - Documentação extensa
    - Suporte robusto
    
    Desvantagens:
    - Taxas maiores (4.99% + R$ 0.40)
    - Webhook pode ter delays
    """
    
    BASE_URL = "https://api.mercadopago.com/v1"
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    async def create_pix_payment(
        self,
        amount: float,
        description: str,
        payer_email: str,
        external_reference: str
    ) -> Dict:
        """
        Cria um pagamento PIX
        
        Returns:
            {
                'id': 'payment_id',
                'status': 'pending',
                'qr_code': 'base64_qr_code',
                'qr_code_base64': 'image_base64',
                'ticket_url': 'url_do_pagamento',
                'expires_at': 'datetime'
            }
        """
        url = f"{self.BASE_URL}/payments"
        
        payload = {
            "transaction_amount": amount,
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": payer_email
            },
            "external_reference": external_reference,
            "notification_url": PaymentConfig.WEBHOOK_URL,
            "date_of_expiration": (
                datetime.now() + timedelta(minutes=PaymentConfig.PIX_EXPIRATION_MINUTES)
            ).isoformat()
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    return {
                        'id': data['id'],
                        'status': data['status'],
                        'qr_code': data['point_of_interaction']['transaction_data']['qr_code'],
                        'qr_code_base64': data['point_of_interaction']['transaction_data']['qr_code_base64'],
                        'ticket_url': data['point_of_interaction']['transaction_data']['ticket_url'],
                        'expires_at': data.get('date_of_expiration')
                    }
                else:
                    error = await resp.text()
                    raise Exception(f"Erro ao criar pagamento: {error}")
    
    async def get_payment_status(self, payment_id: str) -> str:
        """Verifica status do pagamento"""
        url = f"{self.BASE_URL}/payments/{payment_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['status']  # pending, approved, rejected, etc
                return "error"
    
    @staticmethod
    def verify_webhook(request_body: str, signature: str) -> bool:
        """Verifica assinatura do webhook do Mercado Pago"""
        expected_sig = hmac.new(
            PaymentConfig.WEBHOOK_SECRET.encode(),
            request_body.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

# =============================================
# OPENPIX (RECOMENDADO PARA BRASIL)
# =============================================

class OpenPixAPI:
    """
    OpenPix - API brasileira especializada em PIX
    Documentação: https://developers.openpix.com.br/docs/
    
    Vantagens:
    - Taxas menores (1.99%)
    - Webhook instantâneo
    - Feito especificamente para PIX
    - Suporte em português
    - Confirmação automática rápida
    
    Desvantagens:
    - Menos conhecida que Mercado Pago
    
    ** RECOMENDAÇÃO: Use OpenPix para melhor custo-benefício **
    """
    
    BASE_URL = "https://api.openpix.com.br/api/v1"
    
    def __init__(self, app_id: str):
        self.app_id = app_id
        self.headers = {
            "Authorization": app_id,
            "Content-Type": "application/json"
        }
    
    async def create_charge(
        self,
        amount: float,
        correlation_id: str,
        description: str,
        customer_name: str,
        customer_taxid: Optional[str] = None
    ) -> Dict:
        """
        Cria uma cobrança PIX
        
        Returns:
            {
                'id': 'charge_id',
                'correlation_id': 'seu_id_interno',
                'status': 'ACTIVE',
                'value': 1000,  # em centavos
                'brcode': 'codigo_pix_copia_cola',
                'qrcode_image': 'url_da_imagem_qrcode',
                'expires_at': 'datetime'
            }
        """
        url = f"{self.BASE_URL}/charge"
        
        payload = {
            "correlationID": correlation_id,
            "value": int(amount * 100),  # Converte para centavos
            "comment": description,
            "customer": {
                "name": customer_name,
                "taxID": customer_taxid
            },
            "expiresIn": PaymentConfig.PIX_EXPIRATION_MINUTES * 60  # em segundos
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    charge = data['charge']
                    return {
                        'id': charge['correlationID'],
                        'status': charge['status'],
                        'value': charge['value'],
                        'brcode': charge['brCode'],  # Código PIX copia e cola
                        'qrcode_image': charge['qrCodeImage'],  # URL da imagem
                        'expires_at': charge.get('expiresDate')
                    }
                else:
                    error = await resp.text()
                    raise Exception(f"Erro ao criar cobrança: {error}")
    
    async def get_charge(self, charge_id: str) -> Dict:
        """Consulta uma cobrança específica"""
        url = f"{self.BASE_URL}/charge/{charge_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['charge']
                return None
    
    async def list_charges(self, start_date: str = None, end_date: str = None) -> list:
        """Lista cobranças em um período"""
        url = f"{self.BASE_URL}/charge"
        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['charges']
                return []
    
    @staticmethod
    def verify_webhook(payload: Dict, signature: str) -> bool:
        """
        Verifica assinatura do webhook
        OpenPix envia um header 'x-webhook-signature'
        """
        # OpenPix usa HMAC SHA256
        message = str(payload).encode()
        expected_sig = hmac.new(
            PaymentConfig.WEBHOOK_SECRET.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

# =============================================
# ASAAS API (ALTERNATIVA EXCELENTE)
# =============================================

class AsaasAPI:
    """
    Asaas - Excelente para automação
    Documentação: https://docs.asaas.com/
    
    Vantagens:
    - Taxas competitivas (1.99% PIX)
    - API muito completa
    - Webhook confiável
    - Gestão de clientes integrada
    
    Como usar:
    1. Crie conta em https://www.asaas.com/
    2. Gere API Key em Integrações > API Key
    3. Use a chave no .env
    """
    
    BASE_URL = "https://www.asaas.com/api/v3"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "access_token": api_key,
            "Content-Type": "application/json"
        }
    
    async def create_pix_charge(
        self,
        customer_id: str,
        amount: float,
        description: str,
        due_date: str = None
    ) -> Dict:
        """Cria cobrança PIX no Asaas"""
        url = f"{self.BASE_URL}/payments"
        
        if not due_date:
            due_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        payload = {
            "customer": customer_id,
            "billingType": "PIX",
            "value": amount,
            "dueDate": due_date,
            "description": description
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                raise Exception(f"Erro ao criar cobrança: {await resp.text()}")
    
    async def get_pix_qrcode(self, payment_id: str) -> Dict:
        """Obtém QR Code PIX de uma cobrança"""
        url = f"{self.BASE_URL}/payments/{payment_id}/pixQrCode"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None

# =============================================
# GERENCIADOR UNIFICADO
# =============================================

class PaymentManager:
    """Gerenciador que abstrai a API escolhida"""
    
    def __init__(self, provider: str = "openpix"):
        """
        provider: 'mercadopago', 'openpix', ou 'asaas'
        """
        self.provider = provider
        
        if provider == "mercadopago":
            self.api = MercadoPagoAPI(PaymentConfig.MP_ACCESS_TOKEN)
        elif provider == "openpix":
            self.api = OpenPixAPI(PaymentConfig.OPENPIX_APP_ID)
        elif provider == "asaas":
            self.api = AsaasAPI(PaymentConfig.OPENPIX_API_KEY)  # Reusar essa config
        else:
            raise ValueError(f"Provider '{provider}' não suportado")
    
    async def create_payment(
        self,
        amount: float,
        description: str,
        payer_info: Dict
    ) -> Dict:
        """Interface unificada para criar pagamento"""
        if self.provider == "openpix":
            return await self.api.create_charge(
                amount=amount,
                correlation_id=payer_info.get('reference_id'),
                description=description,
                customer_name=payer_info.get('name')
            )
        elif self.provider == "mercadopago":
            return await self.api.create_pix_payment(
                amount=amount,
                description=description,
                payer_email=payer_info.get('email'),
                external_reference=payer_info.get('reference_id')
            )
        # Adicionar outros providers conforme necessário
    
    async def check_payment(self, payment_id: str) -> str:
        """Verifica status do pagamento"""
        if self.provider == "openpix":
            charge = await self.api.get_charge(payment_id)
            return charge.get('status') if charge else 'error'
        elif self.provider == "mercadopago":
            return await self.api.get_payment_status(payment_id)

# =============================================
# EXEMPLO DE USO
# =============================================

async def exemplo_criar_pagamento():
    """Exemplo de como usar o sistema de pagamentos"""
    
    # Inicializar com OpenPix (recomendado)
    payment_manager = PaymentManager(provider="openpix")
    
    # Criar pagamento
    result = await payment_manager.create_payment(
        amount=10.00,
        description="Inscrição Torneio Free Fire",
        payer_info={
            'reference_id': 'inscricao_123',
            'name': 'João Silva',
            'email': 'joao@email.com'
        }
    )
    
    print(f"PIX Copia e Cola: {result['brcode']}")
    print(f"QR Code: {result['qrcode_image']}")
    
    # Verificar pagamento depois
    await asyncio.sleep(60)  # Aguardar 1 minuto
    status = await payment_manager.check_payment(result['id'])
    print(f"Status: {status}")

# =============================================
# CONFIGURAÇÃO DO .env
# =============================================

"""
# Para OpenPix (RECOMENDADO):
OPENPIX_APP_ID=sua_app_id_aqui
OPENPIX_API_KEY=sua_api_key_aqui

# Para Mercado Pago:
MERCADO_PAGO_ACCESS_TOKEN=seu_access_token
MERCADO_PAGO_PUBLIC_KEY=sua_public_key

# Webhook (qualquer provider):
WEBHOOK_URL=https://seu-dominio.com/webhook/payment
WEBHOOK_SECRET=seu_secret_aleatorio_seguro

# Como obter as credenciais:

## OpenPix:
1. Acesse: https://app.openpix.com.br/
2. Crie uma conta
3. Vá em Integrações > API
4. Copie o App ID e API Key

## Mercado Pago:
1. Acesse: https://www.mercadopago.com.br/developers/
2. Crie uma aplicação
3. Copie as credenciais em Produção

## Asaas:
1. Acesse: https://www.asaas.com/
2. Faça cadastro
3. API > Gerar Nova Chave
"""
