from datetime import timedelta
from decimal import Decimal
from io import BytesIO
import uuid

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from erp.models import AuditEvent,Capability,ChemicalProfile,HazardTag,ResourceDocument,StockMovement
from erp.services.common import Conflict,snapshot
from erp.services.safety import (attach_document,document_target,enforce_storage,require_target,save_chemical_profile,
    save_hazard_tag,save_storage_rule,storage_compatibility,target_cost_access)
from erp.services.stock import reconcile_stock,transfer_stock
from erp.services.storage import save_location
from erp.services.work import create_work,delegate_work
from erp.test_operations import OperationFixtures


def pdf_bytes(title='Document de recette'):
    writer=PdfWriter()
    writer.add_blank_page(width=595.28,height=841.89)
    writer.add_metadata({'/Title':title})
    data=BytesIO()
    writer.write(data)
    return data.getvalue()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],SECURE_SSL_REDIRECT=False,
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SafetyDocumentTests(OperationFixtures,TestCase):
    def tag(self,code='GROUP-A'):
        return save_hazard_tag(self.ops,{'code':code,'name':'Groupe documenté '+code,'ghs_code':'GHS05'})

    def profile(self,article,tag):
        return save_chemical_profile(self.ops,article.pk,expected=article.version,tags=[tag],values={
            'classification':'Classification transcrite depuis le document fourni',
            'source_reference':'FDS de recette, version vérifiée','reviewed_on':timezone.localdate()})

    def test_classification_is_never_inferred_and_requires_documented_source(self):
        self.article.cas='50-00-0'
        self.article.save(update_fields=['cas'])
        self.assertFalse(ChemicalProfile.objects.exists())
        self.assertEqual(storage_compatibility(self.article,self.freezer),[])
        tag=self.tag()
        with self.assertRaises(ValidationError):
            save_chemical_profile(self.ops,self.article.pk,expected=self.article.version,tags=[tag],
                values={'classification':'Texte','source_reference':'','reviewed_on':timezone.localdate()})
        profile=self.profile(self.article,tag)
        self.assertEqual(profile.tags.get(),tag)
        self.assertEqual(profile.reviewed_by,self.ops)
        self.assertEqual(profile.source_reference,'FDS de recette, version vérifiée')
        self.article.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            save_chemical_profile(self.operator,self.article.pk,expected=self.article.version,tags=[],values={})

    def test_prohibited_location_blocks_receipt_and_transfer_atomically(self):
        tag=self.tag()
        self.profile(self.article,tag)
        self.article.refresh_from_db()
        rule=save_storage_rule(self.ops,{'location':self.freezer,'mode':'PROHIBITED','first_tag':tag,
            'second_tag':None,'reference':'Procédure de stockage vérifiée','blocking':True,'active':True})
        with self.assertRaises(ValidationError):
            self.receive()
        self.assertFalse(StockMovement.objects.exists())
        room=save_location(self.ops,{'code':'SAFE-LOCATION','name':'Stockage compatible','kind':self.storage_kind,'parent':self.lab})
        container,_,_=self.receive(location=room)
        with self.assertRaises(ValidationError):
            transfer_stock(self.ops,container.pk,key=uuid.uuid4(),destination=self.freezer,reason='Transfert interdit')
        container.refresh_from_db()
        self.assertEqual(container.location_id,room.pk)
        self.assertEqual(reconcile_stock(self.ops),[])
        save_storage_rule(self.ops,{'active':False},pk=rule.pk,expected=rule.version)
        transfer_stock(self.ops,container.pk,key=uuid.uuid4(),destination=self.freezer,reason='Règle levée après vérification')
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_configured_incompatibility_checks_other_stored_groups_not_guessed_chemistry(self):
        first,second=self.tag('GROUP-A'),self.tag('GROUP-B')
        self.profile(self.article,first)
        self.profile(self.liquid,second)
        self.article.refresh_from_db()
        self.liquid.refresh_from_db()
        rule=save_storage_rule(self.ops,{'location':self.freezer,'mode':'INCOMPATIBLE','first_tag':first,
            'second_tag':second,'reference':'Deux groupes incompatibles selon la procédure','blocking':True,'active':True})
        container,_,_=self.receive()
        issues=storage_compatibility(self.liquid,self.freezer)
        self.assertEqual(len(issues),1)
        self.assertTrue(issues[0]['blocking'])
        with self.assertRaises(ValidationError):
            self.receive('LIQUID',article=self.liquid,unit=self.ml)
        rule=save_storage_rule(self.ops,{'blocking':False},pk=rule.pk,expected=rule.version)
        liquid,_,_=self.receive('LIQUID',article=self.liquid,unit=self.ml)
        self.assertTrue(storage_compatibility(self.liquid,self.freezer))
        self.client.force_login(self.ops)
        response=self.client.get(reverse('erp:stock-detail',args=[liquid.pk]))
        self.assertContains(response,'Incompatibilité de stockage configurée')
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_document_versions_keep_original_bytes_hash_and_private_permissions(self):
        data=pdf_bytes()
        first=attach_document(self.ops,'article',self.article.pk,title='FDS de recette',kind='SDS',filename='source.pdf',data=data,
            source='Fabricant, document reçu',documented_on=timezone.localdate())
        self.assertEqual(bytes(first.content),data)
        self.assertEqual(document_target(first),('article',self.article.pk))
        duplicate=attach_document(self.ops,'article',self.article.pk,title='FDS de recette',kind='SDS',filename='renamed.pdf',data=data,source='Document reçu')
        self.assertEqual(first.pk,duplicate.pk)
        self.assertEqual(ResourceDocument.objects.count(),1)
        self.assertNotIn('content',snapshot(first))
        event=AuditEvent.objects.filter(entity_id=first.pk).get()
        self.assertNotIn('content',event.after)
        self.assertEqual(event.after['sha256'],first.sha256)
        second=attach_document(self.ops,'article',self.article.pk,title='FDS mise à jour',kind='SDS',filename='revision.pdf',data=pdf_bytes('Nouvelle source'),
            source='Révision fabricant',supersedes=first)
        self.assertEqual(second.supersedes_id,first.pk)
        with self.assertRaises(Conflict):
            attach_document(self.ops,'article',self.article.pk,title='Autre révision',kind='SDS',filename='new.pdf',data=pdf_bytes('Autre source'),
                source='Source alternative',supersedes=first)
        self.client.force_login(self.ops)
        response=self.client.get(reverse('erp:resource-document-download',args=[first.pk]))
        self.assertEqual(b''.join(response.streaming_content),data)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:resource-document-download',args=[first.pk])).status_code,403)
        with self.assertRaises(ValidationError):
            first.delete()

    def test_financial_attachments_remain_hidden_after_cost_permission_is_withdrawn(self):
        work=create_work(self.ops,kind='CDC',title='Dossier de recette',assignee=self.operator,allow_costs=True)
        document=attach_document(self.operator,'work',work.pk,title='Estimation financière',kind='EVIDENCE',filename='budget.pdf',
            data=pdf_bytes('Budget interne'),source='Estimation interne',financial=True)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(reverse('erp:resource-documents',args=['work',work.pk])),'Estimation financière')
        work=delegate_work(self.ops,work.pk,expected=work.version,assignee=self.operator,allow_costs=False,reason='Accès technique uniquement')
        self.assertNotContains(self.client.get(reverse('erp:resource-documents',args=['work',work.pk])),'Estimation financière')
        self.assertEqual(self.client.get(reverse('erp:resource-document-download',args=[document.pk])).status_code,403)
        with self.assertRaises(PermissionDenied):
            attach_document(self.operator,'work',work.pk,title='Nouvelle estimation',kind='EVIDENCE',filename='new.pdf',
                data=pdf_bytes('Autre budget'),source='Document remplacé',supersedes=document)
        delegate_work(self.ops,work.pk,expected=work.version,assignee=self.second,reason='Réaffectation')
        self.assertEqual(self.client.get(reverse('erp:resource-documents',args=['work',work.pk])).status_code,403)

    def test_file_structure_and_target_consistency_are_checked(self):
        for filename,data in [('bad.exe',b'bad'),('bad.pdf',b'not a pdf'),('empty.pdf',b''),('large.pdf',b'x'*(10*1024*1024+1))]:
            with self.subTest(filename=filename),self.assertRaises(ValidationError):
                attach_document(self.ops,'article',self.article.pk,title='Document',kind='SDS',filename=filename,data=data,source='Source')
        self.assertEqual(ResourceDocument.objects.count(),0)
        document=attach_document(self.ops,'article',self.article.pk,title='FDS',kind='SDS',filename='source.pdf',data=pdf_bytes(),source='Source')
        tag=self.tag()
        with self.assertRaises(ValidationError):
            save_chemical_profile(self.ops,self.liquid.pk,expected=self.liquid.version,tags=[tag],values={
                'classification':'Document reçu','source_reference':'FDS','source_document':document,'reviewed_on':timezone.localdate()})
        with self.assertRaises(ValidationError):
            require_target(self.ops,'unknown',self.article.pk)
        with self.assertRaises(PermissionDenied):
            require_target(AnonymousUser(),'article',self.article.pk)

    def test_native_chemical_rule_and_document_upload_forms(self):
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(reverse('erp:safety')).status_code,200)
        response=self.client.post(reverse('erp:hazard-new'),{'code':'FORM-TAG','name':'Danger transcrit','ghs_code':'GHS05','active':'on'})
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        tag=HazardTag.objects.get(code='FORM-TAG')
        response=self.client.post(reverse('erp:chemical-edit',args=[self.article.pk]),{
            'expected_version':self.article.version,'classification':'Classification depuis la FDS','source_reference':'Source fabricant',
            'reviewed_on':timezone.localdate().isoformat(),'tags':[tag.pk]})
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        response=self.client.post(reverse('erp:storage-rule-new'),{'location':self.freezer.pk,'mode':'PROHIBITED',
            'first_tag':tag.pk,'blocking':'on','active':'on','reference':'Restriction documentaire approuvée'})
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        url=reverse('erp:resource-document-upload',args=['article',self.article.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        response=self.client.post(url,{'title':'FDS de contrôle','kind':'SDS','source':'Document fabricant',
            'file':SimpleUploadedFile('fiche.pdf',pdf_bytes(),content_type='application/pdf')})
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        self.assertContains(self.client.get(reverse('erp:article',args=[self.article.pk])),'Classification depuis la FDS')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:safety')).status_code,403)

    def test_chemical_profile_audit_keeps_selected_groups_before_and_after_updates(self):
        first,second=self.tag('AUDIT-A'),self.tag('AUDIT-B')
        profile=self.profile(self.article,first)
        events=AuditEvent.objects.filter(entity_id=profile.pk,action='chemical_profile_saved').order_by('pk')
        initial=events.get()
        self.assertEqual(initial.before,{})
        self.assertEqual(initial.after['tags'],[first.code])
        self.assertEqual(initial.after['classification'],profile.classification)
        self.article.refresh_from_db()
        save_chemical_profile(self.ops,self.article.pk,expected=self.article.version,
            values={'classification':'Classification révisée sur source vérifiée'},tags=[second])
        updated=events.last()
        self.assertEqual(updated.before['tags'],[first.code])
        self.assertEqual(updated.after['tags'],[second.code])
        self.assertEqual(updated.after['classification'],'Classification révisée sur source vérifiée')
        self.article.refresh_from_db()
        save_chemical_profile(self.ops,self.article.pk,expected=self.article.version,values={},tags=[])
        cleared=events.last()
        self.assertEqual(cleared.before['tags'],[second.code])
        self.assertEqual(cleared.after['tags'],[])
        initial.refresh_from_db()
        self.assertEqual(initial.after['tags'],[first.code])
        self.assertEqual(events.count(),3)

    def test_safety_forms_persist_changes_and_refuse_stale_writes(self):
        from erp.models import StorageSafetyRule
        self.client.force_login(self.ops)
        tag_data = {'code': 'HTTP-HAZARD', 'name': 'Danger documenté', 'ghs_code': 'GHS05',
            'active': 'on', 'expected_version': 1}
        response = self.client.post(reverse('erp:hazard-new'), tag_data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        tag = HazardTag.objects.get(code='HTTP-HAZARD')
        tag_data.update(expected_version=tag.version, name='Désignation révisée')
        self.assertEqual(self.client.post(reverse('erp:hazard-edit', args=[tag.pk]), tag_data).status_code, 302)
        tag_data['name'] = 'Écrasement interdit'
        self.assertEqual(self.client.post(reverse('erp:hazard-edit', args=[tag.pk]), tag_data).status_code, 400)
        tag.refresh_from_db()
        self.assertEqual(tag.name, 'Désignation révisée')
        rule_data = {'location': self.freezer.pk, 'mode': 'PROHIBITED', 'first_tag': tag.pk,
            'blocking': 'on', 'active': 'on', 'reference': 'Procédure vérifiée', 'expected_version': 1}
        response = self.client.post(reverse('erp:storage-rule-new'), rule_data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        rule = StorageSafetyRule.objects.get(first_tag=tag)
        rule_data.update(expected_version=rule.version, reference='Procédure révisée')
        self.assertEqual(self.client.post(reverse('erp:storage-rule-edit', args=[rule.pk]), rule_data).status_code, 302)
        self.assertEqual(self.client.post(reverse('erp:storage-rule-edit', args=[rule.pk]), rule_data).status_code, 400)
        chemical = {'expected_version': self.article.version, 'classification': 'Classification fournie',
            'source_reference': 'FDS vérifiée', 'reviewed_on': timezone.localdate().isoformat(), 'tags': [tag.pk]}
        response = self.client.post(reverse('erp:chemical-edit', args=[self.article.pk]), chemical)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        self.assertEqual(self.client.post(reverse('erp:chemical-edit', args=[self.article.pk]), chemical).status_code, 400)
        self.assertEqual(ChemicalProfile.objects.get(article=self.article).tags.get(), tag)

    def test_document_http_validation_and_read_only_access(self):
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(reverse('erp:resource-documents', args=['article', uuid.uuid4()])).status_code, 404)
        response = self.client.post(reverse('erp:resource-document-upload', args=['article', self.article.pk]),
            {'title': 'Document invalide', 'kind': 'SDS', 'source': 'Source identifiée',
             'file': SimpleUploadedFile('invalid.txt', b'Not a PDF')})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ResourceDocument.objects.exists())
        self.grant(Capability.VIEW_CATALOG, category=self.category)
        self.client.force_login(self.operator)
        response = self.client.get(reverse('erp:resource-documents', args=['article', self.article.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_write'])

    def test_safety_services_reject_protected_fields_and_duplicate_groups(self):
        tag = self.tag()
        with self.assertRaises(ValidationError):
            save_hazard_tag(self.ops, {'version': 900}, pk=tag.pk, expected=tag.version)
        with self.assertRaises(ValidationError):
            save_chemical_profile(self.ops, self.article.pk, expected=self.article.version,
                values={'reviewed_by': self.outsider}, tags=[])
        with self.assertRaises(ValidationError):
            save_chemical_profile(self.ops, self.article.pk, expected=self.article.version,
                values={'classification': 'Source', 'source_reference': 'FDS', 'reviewed_on': timezone.localdate()},
                tags=[tag, tag])
        with self.assertRaises(ValidationError):
            save_storage_rule(self.ops, {'created_by': self.outsider})
        with self.assertRaises(ValidationError):
            save_storage_rule(self.ops, {'location': self.freezer, 'mode': 'INCOMPATIBLE',
                'first_tag': tag, 'second_tag': tag, 'reference': 'Source'})
        with self.assertRaises(ValidationError):
            document_target(ResourceDocument())
        with self.assertRaises(ValidationError):
            attach_document(self.ops, 'article', self.article.pk, title='', kind='SDS', filename='source.pdf',
                data=pdf_bytes(), source='Source')
        self.assertFalse(ChemicalProfile.objects.exists())
        self.assertFalse(ResourceDocument.objects.exists())

    def test_receipt_sample_and_work_document_scopes_and_financial_supersession(self):
        from erp.services.biobank import receive_sample
        container, movement, _ = self.receive()
        work = create_work(self.ops, kind='CONTROL', title='Dossier de contrôle', assignee=self.operator)
        sample = receive_sample(self.ops, key=uuid.uuid4(), code='DOC-SAMPLE', amount=10,
            unit=self.ul, location=self.freezer, received_on=timezone.localdate(), reason='Réception')
        for kind, target in [('receipt', movement.receipt), ('sample', sample), ('work', work)]:
            self.assertEqual(require_target(self.ops, kind, target.pk, write=True), target)
            doc = attach_document(self.ops, kind, target.pk, title='Justificatif', kind='OTHER',
                filename='evidence.pdf', data=pdf_bytes(kind), source='Source contrôlée')
            self.assertEqual(document_target(doc), (kind, target.pk))
            self.assertEqual(target_cost_access(self.ops, kind, target), kind != 'sample')
        finance = attach_document(self.ops, 'article', self.article.pk, title='Document restreint', kind='SDS',
            filename='financial.pdf', data=pdf_bytes('Financial source'), source='Source', financial=True)
        self.grant(Capability.EDIT_CATALOG, category=self.category)
        with self.assertRaises(PermissionDenied):
            attach_document(self.operator, 'article', self.article.pk, title='Révision', kind='SDS',
                filename='revision.pdf', data=pdf_bytes('Financial revision'), source='Nouvelle source', supersedes=finance)
        self.assertFalse(ResourceDocument.objects.filter(supersedes=finance).exists())

    def test_financial_upload_and_cross_target_replacement_are_rejected(self):
        from erp.safety_forms import DocumentForm
        self.grant(Capability.EDIT_CATALOG, category=self.category)
        self.assertEqual(require_target(self.operator, 'article', self.article.pk, write=True), self.article)
        self.assertFalse(target_cost_access(self.operator, 'article', self.article))
        kwargs = dict(title='Source', kind='SDS', filename='source.pdf', data=pdf_bytes('Initial'), source='Fabricant')
        with self.assertRaises(PermissionDenied):
            attach_document(self.operator, 'article', self.article.pk, financial=True, **kwargs)
        original = attach_document(self.ops, 'article', self.liquid.pk, **kwargs)
        kwargs['data'] = pdf_bytes('Replacement')
        with self.assertRaisesRegex(ValidationError, 'même dossier'):
            attach_document(self.ops, 'article', self.article.pk, supersedes=original, **kwargs)
        restricted = attach_document(self.ops, 'article', self.article.pk, financial=True, **kwargs)
        form = DocumentForm(user=self.operator, target_kind='article', target=self.article)
        self.assertNotIn('financial', form.fields)
        self.assertFalse(form.fields['supersedes'].queryset.filter(pk=restricted.pk).exists())
        self.assertEqual(ResourceDocument.objects.count(), 2)
        self.assertFalse(ResourceDocument.objects.filter(supersedes__isnull=False).exists())
